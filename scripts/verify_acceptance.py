#!/usr/bin/env python3
"""Freeze and verify the private codec acceptance set before inference."""
import argparse
from collections import Counter
import json

from avllm_data import (CODECS, ROOT, dev_overlap, evidence_fingerprint, load_dev_exclusions,
                        normalized, read_jsonl, read_split_registry)
from dev_benchmark import file_sha, index, load_key, load_questions, numeric_result, verify_sources
from verify_holdout_draft import calculate as draft_reference

PRIVATE = ROOT / "data/holdout/v2"
LOCK = ROOT / "benchmarks/holdout-v2/manifest.json"


def reference(case):
    p = case["inputs"]
    match case["case"]:
        case "avc_scaling":
            nxt = last = 8
            default = 0
            inc = iter(p["deltas"])
            values = {}
            for j in range(p["size"]):
                if nxt:
                    nxt = (last + next(inc)) & 255
                    default = int(j == 0 and nxt == 0)
                last = nxt or last
                values[f"j{j}"] = last
                if j == 0:
                    values.update(next=nxt, reads_next=int(nxt != 0))
            if next(inc, None) is not None:
                raise ValueError("Unused scaling-list deltas")
            values["default"] = default
            return {k: values[k] for k in p["keys"]}
        case "hevc_ctx":
            hi, lo = divmod(p["init"], 16)
            q = max(0, min(p["qp"], 51))
            raw = ((5 * hi - 45) * q) // 16 + 8 * lo - 16
            pre = max(1, min(raw, 126))
            return {"pre": pre, "mps": int(pre >= 64), "state": abs(pre - 63) - int(pre >= 64)}
        case "vvc_vb":
            a, b = [8 * v + 8 for v in p["minus1"]]
            spacing = abs(b - a)
            return {f"first_{p['axis']}": a, f"second_{p['axis']}": b,
                    "spacing": spacing, "spacing_ok": int(spacing >= p["ctb"])}
        case "av1_tiles":
            sizes = [x + 1 for x in p["sizes_minus1"]]
            overhead = (p["size_bytes_minus1"] + 1) * len(sizes)
            out = {"last": p["after_header"] - sum(sizes) - overhead, "size_fields_bytes": overhead}
            out.update(zip(("first", "second"), sizes))
            return out
        case _:
            return draft_reference(case)


def check():
    questions = index(read_jsonl(PRIVATE / "questions.jsonl"), "questions")
    keys = index(read_jsonl(PRIVATE / "answer-key.jsonl"), "answer key")
    for filename in ("questions.jsonl", "answer-key.jsonl"):
        original = (PRIVATE.parent / "v1-draft" / filename).read_bytes()
        if not (PRIVATE / filename).read_bytes().startswith(original):
            raise ValueError("The original holdout draft must be preserved exactly")
    registry = read_split_registry()
    exclusions = load_dev_exclusions(registry)
    for dataset in sorted((ROOT / "datasets").glob("*/candidates.jsonl")):
        for row in read_jsonl(dataset):
            exclusions["ids"].add(row["id"])
            exclusions["groups"].add(row["split_group"])
            exclusions["prompts"].update(normalized(m["content"]) for m in row["messages"] if m["role"] == "user")
            exclusions["evidence"].update(evidence_fingerprint(ev) for ev in row["evidence"])
    groups = Counter(q["split_group"] for q in questions.values())
    counts = Counter(q["codec"] for q in questions.values())
    if (questions.keys() != keys.keys() or counts != dict.fromkeys(CODECS, 6)
            or len(groups) != 8 or sorted(groups.values()) != [2] * 4 + [4] * 4
            or not set(groups).issubset(registry["groups"])):
        raise ValueError("Unexpected question IDs, coverage or reserved families")
    nums, seen = Counter(), set()
    for ident, q in questions.items():
        prompt = normalized(q["prompt"])
        if not prompt or prompt in seen or not q["evidence"]:
            raise ValueError(f"{ident}: missing or duplicate content")
        seen.add(prompt)
        if dev_overlap(exclusions, sample_id=ident, group=q["split_group"], prompt=prompt, evidence=q["evidence"]):
            raise ValueError(f"{ident}: overlaps training, validation or development")
        key = keys[ident]
        case = key["numeric"]
        if (case is not None) != (q["task_type"] == "calculation"):
            raise ValueError(f"{ident}: numeric assignment differs")
        if case is not None:
            nums[q["codec"]] += 1
            expected = case["expected"]
            if (not expected or any(type(v) is not int for v in expected.values()) or reference(case) != expected
                    or numeric_result(key["reference_answer"], expected) != "correct"):
                raise ValueError(f"{ident}: independent recomputation disagrees")
    if nums != dict.fromkeys(CODECS, 4):
        raise ValueError("Unexpected numeric coverage")
    load_key({"answer_key_sha256": file_sha(PRIVATE / "answer-key.jsonl"),
              "numeric_count": sum(nums.values())}, questions, PRIVATE)
    return {"version": "holdout-v2", "status": "frozen_pilot_not_independently_human_reviewed",
            "question_count": len(questions), "codec_counts": dict(counts), "numeric_count": sum(nums.values()),
            "source_locators_verified": verify_sources(questions), "groups": sorted(groups),
            "questions_sha256": file_sha(PRIVATE / "questions.jsonl"), "answer_key_sha256": file_sha(PRIVATE / "answer-key.jsonl")}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--freeze", action="store_true")
    args = p.parse_args()
    manifest = check()
    payload = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if args.freeze:
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        with LOCK.open("x", encoding="utf-8") as out:
            out.write(payload)
    elif json.loads(LOCK.read_text()) != manifest:
        p.error("Frozen hashes or isolation checks differ")
    local_manifest = PRIVATE / "manifest.json"
    if not local_manifest.exists():
        local_manifest.write_text(payload)
    if json.loads(local_manifest.read_text()) != manifest:
        p.error("Local manifest differs")
    load_key(*load_questions(PRIVATE), PRIVATE)
    print(f"Verified {manifest['question_count']} frozen questions, {manifest['numeric_count']} numeric references, "
          f"{manifest['source_locators_verified']} source locators")


if __name__ == "__main__":
    main()
