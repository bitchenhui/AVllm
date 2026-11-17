#!/usr/bin/env python3
"""Score frozen acceptance runs and enforce paired comparison controls."""
import argparse
from collections import Counter
import json
from pathlib import Path

from avllm_data import read_jsonl, sha
from blind_review import aggregate
from dev_benchmark import file_sha, index, load_key, load_questions, numeric_result
from diagnose_numeric import content_result
from verify_acceptance import LOCK, PRIVATE, reference


def score(base, assisted, tuned, contexts, review):
    manifest, questions = load_questions(PRIVATE)
    if manifest != json.loads(LOCK.read_text()):
        raise ValueError("Question manifest is not frozen")
    keys = load_key(manifest, questions, PRIVATE)
    context_file = contexts / "contexts.jsonl"
    context_manifest = json.loads((contexts / "manifest.json").read_text())
    if (context_manifest["contexts_sha256"] != file_sha(context_file)
            or context_manifest["questions_sha256"] != manifest["questions_sha256"]):
        raise ValueError("Contexts changed or used other questions")
    paths = [base, assisted, tuned]
    runs = [json.loads((p / "manifest.json").read_text()) for p in paths]
    ignored = {"condition", "adapter_file_sha256", "contexts_sha256", "calculator", "predictions_sha256"}
    fixed = {k: v for k, v in runs[0].items() if k not in ignored}
    if (fixed["status"] != "completed" or fixed["questions_sha256"] != manifest["questions_sha256"]
            or any({k: v for k, v in r.items() if k not in ignored} != fixed for r in runs[1:])):
        raise ValueError("Fixed inference controls differ")
    if ([r["condition"] for r in runs] != ["A", "B", "D"] or runs[0]["contexts_sha256"] is not None
            or any(r["adapter_file_sha256"] for r in runs[:2]) or not runs[2]["adapter_file_sha256"]
            or any(r["contexts_sha256"] != context_manifest["contexts_sha256"] for r in runs[1:])
            or "calculator" in runs[0] or runs[1].get("calculator") != runs[2].get("calculator")
            or not runs[1].get("calculator")):
        raise ValueError("Expected base / same retrieval and calculator / same retrieval and calculator with adapter")
    review_hashes = {}
    reviewed = None
    if review:
        files = [review / f for f in ("queue.jsonl", "private-identities.jsonl", "ratings.jsonl")]
        reviewed = aggregate(*(read_jsonl(p) for p in files))
        review_hashes = {p.name: file_sha(p) for p in files}
        if set(reviewed["totals"]) != {p.name for p in paths}:
            raise ValueError("Review run set differs")
    numeric = {ident: reference(k["numeric"]) for ident, k in keys.items() if k["numeric"] is not None}
    scored = []
    for path, run in zip(paths, runs):
        file = path / "predictions.jsonl"
        if file_sha(file) != run["predictions_sha256"]:
            raise ValueError(f"Predictions changed: {path}")
        rows = index(read_jsonl(file), path.name)
        if rows.keys() != questions.keys():
            raise ValueError(f"Prediction IDs differ: {path}")
        items = {q: {"strict": numeric_result(rows[q]["answer"], e), "content": content_result(rows[q]["answer"], e)}
                 for q, e in numeric.items()}
        codes = {}
        for codec in manifest["codec_counts"]:
            subset = [v for q, v in items.items() if questions[q]["codec"] == codec]
            codes[codec] = {"numeric_total": len(subset),
                            "strict_correct": sum(v["strict"] == "correct" for v in subset),
                            "content_correct": sum(v["content"] == "correct" for v in subset)}
        errors = 0
        for row in rows.values():
            errors += sum(c["result"].startswith("error:") for c in row.get("calculator_calls", []))
        entry = {"condition": run["condition"], "local_run": str(path), "manifest_sha256": file_sha(path / "manifest.json"),
                 "predictions_sha256": file_sha(file), "adapter_file_sha256": run["adapter_file_sha256"],
                 "numeric_total": len(items), "numeric_items": items,
                 "strict_numeric": dict(Counter(v["strict"] for v in items.values())),
                 "numeric_content": dict(Counter(v["content"] for v in items.values())), "by_codec": codes,
                 "truncated": sum(r["finish_reason"] == "length" for r in rows.values()),
                 "numeric_truncated": sum(rows[q]["finish_reason"] == "length" for q in items),
                 "tool_calls": sum(len(r.get("calculator_calls", [])) for r in rows.values()),
                 "questions_with_tool_calls": sum(bool(r.get("calculator_calls")) for r in rows.values()),
                 "tool_errors": errors, "tokens_generated": sum(r["generation_tokens"] for r in rows.values()),
                 "prompt_tokens_including_tool_rounds": sum(r["prompt_tokens"] for r in rows.values()),
                 "seconds_excluding_model_load": round(sum(r["seconds"] for r in rows.values()), 4)}
        if reviewed:
            ratings = [r for r in reviewed["items"] if r["run"] == path.name]
            if (len(ratings) != len(questions) - len(numeric) or {r["id"] for r in ratings} != set(questions) - set(numeric)
                    or any(r["answer_sha256"] != sha(rows[r["id"]]["answer"].encode()) for r in ratings)):
                raise ValueError(f"Stale review: {path}")
            entry["non_numeric_ai_review"] = reviewed["totals"][path.name]
            for codec, counts in codes.items():
                subset = [r for r in ratings if questions[r["id"]]["codec"] == codec]
                counts.update(review_points=sum(sum(r["points"].values()) for r in subset),
                              review_points_possible=sum(len(r["points"]) for r in subset))
        scored.append(entry)
    evidence_pages = {"any_frozen_reference_page": 0, "all_frozen_reference_pages": 0}
    for ident, q in questions.items():
        expected = {e["locator"]["page"] for e in q["evidence"] if e["locator"]["type"] == "pdf_page"}
        found = {e["page"] for e in context_manifest["items"][ident]}
        if expected:
            evidence_pages["any_frozen_reference_page"] += int(bool(expected & found))
            evidence_pages["all_frozen_reference_pages"] += int(expected <= found)
    paired = {}
    for left, right in ((0, 1), (1, 2), (0, 2)):
        first, second = scored[left], scored[right]
        for metric in ("strict", "content"):
            pairs = [(first["numeric_items"][q][metric] == "correct", second["numeric_items"][q][metric] == "correct")
                     for q in numeric]
            paired[f"{first['condition']}_to_{second['condition']}_{metric}"] = {
                "gain": sum(not a and b for a, b in pairs), "loss": sum(a and not b for a, b in pairs),
                "same_correct": sum(a and b for a, b in pairs), "same_not_correct": sum(not a and not b for a, b in pairs)}
    return {"benchmark": manifest, "paired_controls": fixed, "calculator": runs[1]["calculator"],
            "contexts_sha256": file_sha(context_file), "retrieval_manifest_sha256": file_sha(contexts / "manifest.json"),
            "retrieval": {k: context_manifest[k] for k in ("method", "source_lock_sha256", "extraction_sha256")},
            "retrieval_page_hits": evidence_pages, "review_hashes": review_hashes,
            "numeric_pair_transitions": paired, "runs": scored}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "assisted", "tuned", "contexts", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--review", type=Path)
    args = parser.parse_args()
    result = score(args.base, args.assisted, args.tuned, args.contexts, args.review)
    with args.output.open("x", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    for r in result["runs"]:
        print(r["condition"], r["strict_numeric"], r["numeric_content"], r.get("non_numeric_ai_review"),
              "truncated", r["truncated"], "tool calls", r["tool_calls"])


if __name__ == "__main__":
    main()
