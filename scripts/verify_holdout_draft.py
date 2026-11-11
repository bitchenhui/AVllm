#!/usr/bin/env python3
"""Verify the private, hash-pinned final benchmark draft against existing splits."""
import argparse
from collections import Counter
import json

from avllm_data import (
    CODECS, ROOT, TASKS, dev_overlap, evidence_fingerprint, load_dev_exclusions,
    normalized, read_jsonl, read_split_registry,
)
from dev_benchmark import file_sha, index, numeric_result, verify_sources

PRIVATE = ROOT / "data/holdout/v1-draft"
MANIFEST = ROOT / "benchmarks/holdout-v1/manifest.json"


def calculate(case):
    p = case["inputs"]
    match case["case"]:
        case "avc_gap_wrap":
            count = (p["current"] - p["previous"] - 1) % p["max"]
            return {"missing_count": count, "first_missing": (p["previous"] + 1) % p["max"],
                    "last_missing": (p["current"] - 1) % p["max"]}
        case "hevc_uni_weight":
            shift = p["denom"] + max(2, 14 - p["bit_depth"])
            scale = 1 << shift
            unclipped = (2 * p["pred"] * p["weight"] + scale) // (2 * scale) + p["offset"]
            return {"log2_wd": shift, "before_clip": unclipped,
                    "prediction_sample": min((1 << p["bit_depth"]) - 1, max(0, unclipped))}
        case "vvc_translational_amvr":
            shift = (3, 4, 6)[p["precision_idx"]]
            return {"amvr_shift": shift, "mvd_x": p["x"] * (1 << shift), "mvd_y": p["y"] * (1 << shift)}
        case "av1_primary_reference":
            slot = p["mapping"][p["primary"]]
            return {"cdf_slot": slot, "prev_frame": slot}
        case _:
            raise ValueError(f"Unknown holdout numeric case: {case['case']}")


def check():
    question_file, key_file = PRIVATE / "questions.jsonl", PRIVATE / "answer-key.jsonl"
    questions = index(read_jsonl(question_file), "holdout questions")
    keys = index(read_jsonl(key_file), "holdout answer key")
    if questions.keys() != keys.keys():
        raise ValueError("Holdout questions and answer key do not match")
    registry = read_split_registry()
    exclusions = load_dev_exclusions(registry)
    for path in ("datasets/pilot-v1/candidates.jsonl", "datasets/validation-v1/candidates.jsonl",
                 "datasets/boundary-v1/candidates.jsonl"):
        for row in read_jsonl(ROOT / path):
            exclusions["ids"].add(row["id"])
            exclusions["groups"].add(row["split_group"])
            exclusions["prompts"].update(normalized(m["content"]) for m in row["messages"] if m["role"] == "user")
            exclusions["evidence"].update(evidence_fingerprint(ev) for ev in row["evidence"])
    groups = {row["split_group"] for row in questions.values()}
    counts = Counter(row["codec"] for row in questions.values())
    if not groups.issubset(registry["groups"]) or len(groups) != 4 or counts != dict.fromkeys(CODECS, 2):
        raise ValueError("Expected four reserved families and two questions per codec")
    prompts = set()
    numeric_counts = Counter()
    for ident, q in questions.items():
        key = keys[ident]
        prompt = normalized(q["prompt"])
        if not prompt or prompt in prompts or not q["evidence"] or q["task_type"] not in TASKS:
            raise ValueError(f"{ident}: duplicate/empty prompt, missing evidence or invalid task")
        prompts.add(prompt)
        if dev_overlap(exclusions, sample_id=ident, group=q["split_group"], prompt=q["prompt"], evidence=q["evidence"]):
            raise ValueError(f"{ident}: overlaps a training, validation or development item")
        if not key["reference_answer"].strip() or not key["rubric"] or any(
                not p["description"].strip() for p in index(key["rubric"], f"{ident} rubric").values()):
            raise ValueError(f"{ident}: missing key or rubric")
        case = key["numeric"]
        if (case is not None) != (q["task_type"] == "calculation"):
            raise ValueError(f"{ident}: numeric key/task mismatch")
        if case is not None:
            numeric_counts[q["codec"]] += 1
            if calculate(case) != case["expected"] or numeric_result(key["reference_answer"], case["expected"]) != "correct":
                raise ValueError(f"{ident}: numeric reference disagrees with stored answer")
    if numeric_counts != dict.fromkeys(CODECS, 1):
        raise ValueError("Expected one numeric question per codec")
    return {"version": "holdout-v1-draft", "status": "hash_pinned_pending_independent_review",
            "question_count": len(questions), "codec_counts": dict(counts),
            "numeric_count": sum(numeric_counts.values()), "source_locators_verified": verify_sources(questions),
            "groups": sorted(groups), "questions_sha256": file_sha(question_file), "answer_key_sha256": file_sha(key_file)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--init-manifest", action="store_true", help="Write the draft lock once; refuse overwrite")
    args = parser.parse_args()
    try:
        verified = check()
        if args.init_manifest:
            with MANIFEST.open("x", encoding="utf-8") as out:
                json.dump(verified, out, ensure_ascii=False, indent=2)
                out.write("\n")
        elif json.loads(MANIFEST.read_text()) != verified:
            raise ValueError("Private draft files differ from the recorded manifest")
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        parser.exit(1, f"{exc}\n")
    print(f"Verified {verified['question_count']} private questions, {verified['numeric_count']} numeric references, "
          f"{verified['source_locators_verified']} evidence locators; pending independent review")


if __name__ == "__main__":
    main()
