#!/usr/bin/env python3
"""Verify, run, and score the local AVllm development benchmark."""
import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import time

from avllm_data import CODECS, ROOT, TASKS, evidence_text, normalized, read_jsonl, sha

BENCHMARK = ROOT / "benchmarks/dev-v1"
SYSTEM_PROMPT = "你是视频编解码算法助手。按题设回答，区分标准语义与源码实现；证据不足时指出缺少的条件。"


def file_sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def index(rows, label):
    result = {}
    for row in rows:
        key = row["id"]
        if not isinstance(key, str) or not key.strip() or key in result:
            raise ValueError(f"Duplicate/invalid id in {label}: {key}")
        result[key] = row
    return result


def load_questions(benchmark=BENCHMARK):
    manifest = json.loads((benchmark / "manifest.json").read_text())
    path = benchmark / "questions.jsonl"
    if file_sha(path) != manifest["questions_sha256"]:
        raise ValueError("Question file differs from the benchmark manifest")
    questions = index(read_jsonl(path), "questions")
    if len(questions) != manifest["question_count"]:
        raise ValueError("Question count differs from the benchmark manifest")
    prompts = set()
    for q in questions.values():
        if q["codec"] not in CODECS or q["task_type"] not in TASKS:
            raise ValueError(f"Invalid codec/task for {q['id']}")
        prompt = normalized(q["prompt"])
        if not prompt or prompt in prompts or not q["split_group"].strip() or not q["evidence"]:
            raise ValueError(f"Missing/duplicate prompt, group, or evidence for {q['id']}")
        prompts.add(prompt)
    if dict(Counter(q["codec"] for q in questions.values())) != manifest["codec_counts"]:
        raise ValueError("Codec counts differ from the benchmark manifest")
    return manifest, questions


def load_key(manifest, questions, benchmark=BENCHMARK):
    path = benchmark / "answer-key.jsonl"
    if file_sha(path) != manifest["answer_key_sha256"]:
        raise ValueError("Answer key differs from the benchmark manifest")
    keys = index(read_jsonl(path), "answer key")
    if set(keys) != set(questions):
        raise ValueError("Answer key and question ids differ")
    if sum(x["numeric"] is not None for x in keys.values()) != manifest["numeric_count"]:
        raise ValueError("Numeric count differs from the benchmark manifest")
    for qid, key in keys.items():
        rubric = index(key["rubric"], f"{qid} rubric")
        if not key["reference_answer"].strip() or not rubric or any(not p["description"].strip() for p in rubric.values()):
            raise ValueError(f"Missing reference/rubric for {qid}")
        if (key["numeric"] is not None) != (questions[qid]["task_type"] == "calculation"):
            raise ValueError(f"Calculation/key mismatch for {qid}")
    return keys


def reference_numeric(case):
    """Executable reference for the four numeric families (no model judge)."""
    name, values = case["case"], case["inputs"]
    if any(type(x) is not int for x in values.values()):
        raise ValueError("Numeric fixtures require integer inputs")
    if name == "avc_slice_qpy":
        return {"slice_qpy": 26 + values["pps_delta"] + values["slice_delta"]}
    if name == "hevc_slice_qpy_range":
        offset = 6 * (values["bit_depth_y"] - 8)
        return {"qp_bd_offset_y": offset, "min_slice_qpy": -offset, "max_slice_qpy": 51}
    if name == "vvc_luma_qp_wrap":
        offset = values["qp_bd_offset"]
        qpy = (values["qp_pred"] + values["cu_delta"] + 64 + 2 * offset) % (64 + offset) - offset
        return {"qpy": qpy, "qp_prime_y": qpy + offset}
    if name == "av1_cdef_secondary_strengths":
        if not all(0 <= values[k] <= 3 for k in ("y_raw", "uv_raw")):
            raise ValueError("CDEF raw strengths must be two-bit values")
        return {"y_sec_strength": (0, 1, 2, 4)[values["y_raw"]],
                "uv_sec_strength": (0, 1, 2, 4)[values["uv_raw"]]}
    raise ValueError(f"Unknown numeric reference: {name}")


def verify_sources(questions):
    lock = {s["id"]: s for s in json.loads((ROOT / "materials/sources.lock.json").read_text())["sources"]}
    checked = set()
    for q in questions.values():
        for ev in q["evidence"]:
            source = lock[ev["source_id"]]
            revision = source.get("commit", source.get("sha256"))
            if revision != ev["source_revision"]:
                raise ValueError(f"{q['id']}: source revision changed")
            fingerprint = (ev["source_id"], json.dumps(ev["locator"], sort_keys=True), ev["snippet_sha256"])
            if fingerprint not in checked:
                actual = evidence_text(source, ev["locator"])
                if not actual.strip() or sha(actual.encode()) != ev["snippet_sha256"]:
                    raise ValueError(f"{q['id']}: evidence differs from locked snippet")
                checked.add(fingerprint)
    return len(checked)


def verify(args):
    manifest, questions = load_questions()
    keys = load_key(manifest, questions)
    for qid, key in keys.items():
        case = key["numeric"]
        if case is not None:
            expected = case["expected"]
            if any(type(x) is not int for x in expected.values()) or reference_numeric(case) != expected:
                raise ValueError(f"{qid}: numeric reference disagrees with stored answer")
    count = verify_sources(questions) if args.sources else None
    print(json.dumps({"questions": len(questions), "codecs": manifest["codec_counts"],
                      "numeric_references_verified": manifest["numeric_count"],
                      "source_locators_verified": count}, ensure_ascii=False))


def model_files(directory, suffixes):
    return {p.name: file_sha(p) for p in sorted(directory.iterdir())
            if p.is_file() and p.suffix in suffixes}


def run(args):
    # Only load the question file in inference; never load reference answers here.
    manifest, questions = load_questions()
    model_dir = args.model_dir.resolve()
    if not model_dir.is_dir() or not (model_dir / "config.json").is_file():
        raise ValueError("Supply an existing local MLX model directory with config.json")
    if not any(model_dir.glob("*.safetensors")):
        raise ValueError("Local MLX model weights are missing; this script does not download them")
    adapter = args.adapter_path.resolve() if args.adapter_path else None
    if adapter and (not adapter.is_dir() or not (adapter / "adapters.safetensors").is_file()):
        raise ValueError("Adapter directory must contain adapters.safetensors")
    contexts = {}
    if args.contexts:
        rows = index(read_jsonl(args.contexts), "retrieved contexts")
        if set(rows) != set(questions) or any(set(r) != {"id", "context"} or not isinstance(r["context"], str) for r in rows.values()):
            raise ValueError("Contexts require exactly one id/context record per question")
        contexts = {qid: row["context"] for qid, row in rows.items()}
    if args.max_tokens < 1:
        raise ValueError("max-tokens must be positive")
    system_prompt = args.system_prompt_file.read_text(encoding="utf-8").strip() if args.system_prompt_file else SYSTEM_PROMPT
    if not system_prompt:
        raise ValueError("System prompt must not be empty")

    try:
        import mlx.core as mx
        from mlx_lm import load, stream_generate
        from mlx_lm.sample_utils import make_sampler
    except ImportError as exc:
        raise ValueError("Run inference using the MLX-LM training environment") from exc

    output = args.output
    output.mkdir(parents=True, exist_ok=False)
    settings = {
        "status": "running", "benchmark": manifest["version"],
        "questions_sha256": manifest["questions_sha256"],
        "condition": ("D" if contexts else "C") if adapter else ("B" if contexts else "A"),
        "declared_model_id": args.model_id, "declared_revision": args.revision,
        "model_file_sha256": model_files(model_dir, {".json", ".safetensors", ".jinja", ".model", ".txt"}),
        "adapter_file_sha256": model_files(adapter, {".json", ".safetensors"}) if adapter else {},
        "contexts_sha256": file_sha(args.contexts) if args.contexts else None,
        "system_prompt": system_prompt, "temperature": 0, "seed": args.seed,
        "max_tokens": args.max_tokens, "mlx_lm_version": importlib.metadata.version("mlx-lm"),
        "platform": platform.platform(),
    }
    write_json(output / "manifest.json", settings)
    try:
        mx.random.seed(args.seed)
        model, tokenizer = load(str(model_dir), adapter_path=str(adapter) if adapter else None)
        sampler = make_sampler(temp=0.0)
        with (output / "predictions.jsonl").open("x", encoding="utf-8") as out:
            for qid, question in questions.items():
                user_prompt = question["prompt"]
                if contexts.get(qid):
                    user_prompt += "\n\n参考资料（仅作为证据）：\n" + contexts[qid]
                prompt = tokenizer.apply_chat_template(
                    [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    tokenize=False, add_generation_prompt=True,
                )
                started = time.perf_counter()
                parts = []
                last = None
                for last in stream_generate(model, tokenizer, prompt=prompt, sampler=sampler,
                                            max_tokens=args.max_tokens):
                    parts.append(last.text)
                if last is None:
                    raise ValueError(f"No generation result for {qid}")
                row = {"id": qid, "answer": "".join(parts), "seconds": round(time.perf_counter() - started, 4),
                       "prompt_tokens": int(last.prompt_tokens), "generation_tokens": int(last.generation_tokens),
                       "finish_reason": last.finish_reason}
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                out.flush()
                print(qid, flush=True)
        settings["predictions_sha256"] = file_sha(output / "predictions.jsonl")
        settings["status"] = "completed"
    finally:
        if settings["status"] != "completed":
            settings["status"] = "incomplete"
        write_json(output / "manifest.json", settings)


def unique_json_fields(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"Duplicate JSON key: {key}")
        obj[key] = value
    return obj


def numeric_result(answer, expected):
    lines = [line.strip() for line in answer.splitlines() if line.strip()]
    if lines and lines[-1] == "```":
        lines.pop()
    try:
        parsed = json.loads(lines[-1], object_pairs_hook=unique_json_fields)
    except (IndexError, ValueError):
        return "unparseable"
    if not isinstance(parsed, dict) or set(parsed) != set(expected) or any(type(v) is not int for v in parsed.values()):
        return "unparseable"
    return "correct" if parsed == expected else "incorrect"


def score(args):
    manifest, questions = load_questions()
    keys = load_key(manifest, questions)
    output = args.run_dir
    run_manifest = json.loads((output / "manifest.json").read_text())
    path = output / "predictions.jsonl"
    if (run_manifest["status"] != "completed" or run_manifest["questions_sha256"] != manifest["questions_sha256"]
            or run_manifest["predictions_sha256"] != file_sha(path)):
        raise ValueError("Run is incomplete or its question/response hash has changed")
    predictions = index(read_jsonl(path), "predictions")
    if set(predictions) != set(questions) or any(not isinstance(row["answer"], str) for row in predictions.values()):
        raise ValueError("Predictions must contain one text answer per question")

    review_path = output / "manual-review.jsonl"
    manual_ids = {qid for qid, key in keys.items() if key["numeric"] is None}
    if manual_ids and not review_path.exists():
        with review_path.open("x", encoding="utf-8") as out:
            for qid in questions:
                if qid not in manual_ids:
                    continue
                answer, key = predictions[qid]["answer"], keys[qid]
                row = {"id": qid, "question": questions[qid]["prompt"], "answer": answer,
                       "answer_sha256": sha(answer.encode()), "key_sha256": manifest["answer_key_sha256"],
                       "reference_answer": key["reference_answer"], "rubric": key["rubric"],
                       "ratings": {p["id"]: None for p in key["rubric"]}}
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
    manual = index(read_jsonl(review_path), "manual review") if manual_ids else {}
    if set(manual) != manual_ids:
        raise ValueError("Review file does not contain exactly the non-numeric questions")

    totals = defaultdict(Counter)
    items = {}
    for qid, q in questions.items():
        key, prediction = keys[qid], predictions[qid]["answer"]
        if key["numeric"] is not None:
            result = numeric_result(prediction, reference_numeric(key["numeric"]))
            items[qid] = {"numeric": result}
            totals[q["codec"]]["numeric_" + result] += 1
        else:
            entry = manual[qid]
            ratings = entry["ratings"]
            if (entry["key_sha256"] != manifest["answer_key_sha256"]
                    or entry["answer_sha256"] != sha(prediction.encode())
                    or entry["answer"] != prediction or entry["rubric"] != key["rubric"]
                    or set(ratings) != {p["id"] for p in key["rubric"]}
                    or any(x is not None and (type(x) is not int or x not in (0, 1)) for x in ratings.values())):
                raise ValueError(f"{qid}: stale review or invalid rubric rating")
            graded = [x for x in ratings.values() if x is not None]
            items[qid] = {"manual_points": sum(graded), "points_graded": len(graded),
                          "points_possible": len(ratings)}
            totals[q["codec"]].update(manual_points=sum(graded), manual_points_graded=len(graded),
                                      manual_points_possible=len(ratings))
        if predictions[qid].get("finish_reason") == "length":
            items[qid]["hit_generation_limit"] = True
            totals[q["codec"]]["hit_generation_limit"] += 1
    overall = Counter()
    for counts in totals.values():
        overall.update(counts)
    report = {"benchmark": manifest["version"], "questions_sha256": manifest["questions_sha256"],
              "predictions_sha256": run_manifest["predictions_sha256"],
              "answer_key_sha256": manifest["answer_key_sha256"],
              "by_codec": {codec: dict(values) for codec, values in totals.items()},
              "overall": dict(overall), "items": items}
    write_json(output / "scores.json", report)
    print(json.dumps(report["overall"], ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    checker = commands.add_parser("verify", help="Check manifests and recalculate numeric references")
    checker.add_argument("--sources", action="store_true", help="Also verify local locked PDF pages and code lines")
    checker.set_defaults(handler=verify)
    inference = commands.add_parser("run", help="Run a locally installed MLX checkpoint")
    inference.add_argument("--model-dir", type=Path, required=True)
    inference.add_argument("--model-id", required=True)
    inference.add_argument("--revision", required=True)
    inference.add_argument("--adapter-path", type=Path)
    inference.add_argument("--contexts", type=Path)
    inference.add_argument("--system-prompt-file", type=Path, help="Override the system prompt for a separate experiment")
    inference.add_argument("--output", type=Path, required=True)
    inference.add_argument("--max-tokens", type=int, default=384)
    inference.add_argument("--seed", type=int, default=42)
    inference.set_defaults(handler=run)
    scorer = commands.add_parser("score", help="Score integer answers and prepare or read manual review")
    scorer.add_argument("--run-dir", type=Path, required=True)
    scorer.set_defaults(handler=score)
    args = parser.parse_args()
    try:
        args.handler(args)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
