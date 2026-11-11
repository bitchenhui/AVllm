#!/usr/bin/env python3
"""Recheck the pilot's locked evidence, split isolation, and integer answers."""
import argparse
from collections import Counter
import json
from pathlib import Path

from avllm_data import (
    ROOT, bounded_path, dev_overlap, evidence_fingerprint, load_dev_exclusions,
    read_jsonl, read_split_registry, registered_split, sha, validate,
)
from dev_benchmark import numeric_result

BATCH = ROOT / "datasets/pilot-v1"
REPORT = BATCH / "verification-report.json"


def integers(values):
    if any(type(x) is not int for x in values):
        raise ValueError("Expected integer fixture parameters")


def avc_dc(params):
    depth, top, left = params["bit_depth_y"], params["top"], params["left"]
    integers([depth])
    if not 8 <= depth <= 14 or len(top) != 4 or len(left) != 4:
        raise ValueError("Expected AVC luma bit depth and four entries on each side")
    samples = []
    for side in (top, left):
        present = [x for x in side if x is not None]
        integers(present)
        if any(not 0 <= x < 2 ** depth for x in present):
            raise ValueError("Neighbour out of range for bit depth")
        if len(present) == 4:
            samples.extend(present)
    if not samples:
        return 2 ** (depth - 1)
    average, remainder = divmod(sum(samples), len(samples))
    return average + int(2 * remainder >= len(samples))


def reference(case):
    params = case["inputs"]
    name = case["operation"]
    if name == "avc_dc":
        return {"dc": avc_dc(params)}
    if name == "avc_dc_pair":
        return {f"dc_{label}": avc_dc(params[label]) for label in ("a", "b")}
    integers(params.values())
    if name == "hevc_merge":
        minus = params["five_minus_max_num_merge_cand"]
        if not 0 <= minus <= 4:
            raise ValueError("HEVC base merge limit outside 1–5")
        return {"max_num_merge_cand": 5 - minus, "max_merge_idx": 4 - minus,
                "merge_idx_present": int(minus != 4)}
    if name in {"vvc_history_poc", "vvc_explicit_poc"}:
        cycle, lsb = params["max_lsb"], params["current_lsb"]
        if cycle < 2 or cycle & (cycle - 1) or not 0 <= lsb < cycle:
            raise ValueError("Invalid VVC POC LSB range")
        if name == "vvc_explicit_poc":
            if params["cycle_value"] < 0:
                raise ValueError("Negative signalled POC cycle")
            poc = cycle * params["cycle_value"] + lsb
        else:
            prev_msb, prev_lsb = params["prev_msb"], params["prev_lsb"]
            if prev_msb % cycle or not 0 <= prev_lsb < cycle:
                raise ValueError("Invalid previous POC components")
            prev = prev_msb + prev_lsb
            # Equivalent to the standard's branch rules away from half-cycle
            # ties: find the closest POC congruent to the signalled LSB.
            poc = min((prev_msb + lsb + k * cycle for k in (-1, 0, 1)),
                      key=lambda value: abs(value - prev))
            if 2 * abs(poc - prev) == cycle:
                raise ValueError("Half-cycle conformance boundary is outside pilot scope")
        return {"poc_msb": poc - lsb, "poc": poc}
    if name == "av1_superres":
        denom = 9 + params["coded_denom"]
        if not 9 <= denom <= 16 or params["width"] <= 0 or params["height"] <= 0:
            raise ValueError("Invalid superres parameters")
        width, remainder = divmod(8 * params["width"], denom)
        width += int(2 * remainder >= denom)
        if width < 16:
            raise ValueError("Small-dimension constraints are outside pilot scope")
        return {"superres_denom": denom, "frame_width": width, "frame_height": params["height"]}
    raise ValueError(f"Unknown reference operation: {name}")


def verify():
    dataset = BATCH / "candidates.jsonl"
    fixture = BATCH / "numeric-cases.json"
    rows = read_jsonl(dataset)
    failures = validate(rows)
    if failures:
        raise ValueError("\n".join(failures))
    registry = read_split_registry()
    exclusions = load_dev_exclusions(registry)
    cases = json.loads(fixture.read_text())["cases"]
    expected_ids = {r["id"] for r in rows if r["task_type"] == "calculation"}
    if set(cases) != expected_ids:
        raise ValueError("Numeric fixture IDs differ from calculation sample IDs")

    numeric = {}
    scopes = set()
    for row in rows:
        qid = row["id"]
        prompt, answer = [m["content"] for m in row["messages"]]
        overlap = dev_overlap(exclusions, sample_id=qid, group=row["split_group"],
                              prompt=prompt, evidence=row["evidence"])
        if overlap or registered_split(row["split_group"], registry) != "train":
            raise ValueError(f"{qid}: evidence or group is reserved for evaluation ({overlap or 'split'})")
        if row["verification"]["status"] != "pending" or row["eligibility"]["status"] != "pending":
            raise ValueError(f"{qid}: this report is for pre-approval candidates only")
        required = {"evidence", "conditions"}
        if qid in cases:
            required.add("calculation")
        if row["task_type"] == "source_code":
            required.add("code")
        checks = {c["kind"]: c for c in row["verification"]["checks"]}
        if set(checks) != required or any(c["result"] != "passed" for c in checks.values()):
            raise ValueError(f"{qid}: missing check record")
        for check in checks.values():
            artifact = bounded_path(ROOT, check["artifact"])
            if artifact != REPORT and (not artifact.is_file() or artifact.stat().st_size == 0):
                raise ValueError(f"{qid}: missing review artifact")
        scopes.update(evidence_fingerprint(ev) for ev in row["evidence"])
        if qid in cases:
            case = cases[qid]
            if sha(prompt.encode()) != case["prompt_sha256"]:
                raise ValueError(f"{qid}: prompt changed after numeric fixture was recorded")
            values = reference(case)
            integers(case["expected"].values())
            if values != case["expected"] or numeric_result(answer, values) != "correct":
                raise ValueError(f"{qid}: answer disagrees with independent integer check")
            numeric[qid] = values

    codec_counts = Counter(r["codecs"][0] for r in rows)
    if codec_counts != dict.fromkeys(("h264", "h265", "h266", "av1"), 4):
        raise ValueError("Expected four samples per codec in this pilot")
    return {
        "batch": "pilot-v1", "status": "candidate_checks_passed_pending_domain_approval",
        "candidates_sha256": sha(dataset.read_bytes()), "numeric_cases_sha256": sha(fixture.read_bytes()),
        "samples": len(rows), "codec_counts": dict(codec_counts), "locked_locators_checked": len(scopes),
        "groups": sorted({r["split_group"] for r in rows}), "numeric_answers": numeric,
        "source_code_reviews": sum(r["task_type"] == "source_code" for r in rows),
        "development_overlaps": 0, "training_approved": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-report", action="store_true", help="Update the committed verification snapshot")
    args = parser.parse_args()
    try:
        result = verify()
        if args.write_report:
            REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        elif json.loads(REPORT.read_text()) != result:
            raise ValueError("Recorded report differs from current checks; investigate before regenerating")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"{exc}\n")
    print(f"{result['samples']} candidates, {result['locked_locators_checked']} evidence locators, "
          f"{len(result['numeric_answers'])} numeric answers, {result['source_code_reviews']} code reviews; "
          "no development overlap; formal approval pending")


if __name__ == "__main__":
    main()
