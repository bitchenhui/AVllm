#!/usr/bin/env python3
"""Recompute and check the phase-one integer and branch candidates."""
import argparse
from collections import Counter
import json

from avllm_data import (
    CODECS, ROOT, dev_overlap, evidence_fingerprint, load_dev_exclusions,
    read_jsonl, read_split_registry, registered_split, sha, validate,
)
from dev_benchmark import file_sha, numeric_result, write_json

BATCH = ROOT / "datasets/boundary-v1"


def crop_rectangle(width, height, subsampling, frame_only, offsets):
    dx, dy = subsampling if subsampling is not None else (1, 1)
    dy *= 2 - frame_only
    left, right, top, bottom = offsets if offsets is not None else (0, 0, 0, 0)
    x0, x1 = left * dx, width - right * dx - 1
    y0, y1 = top * dy, height - bottom * dy - 1
    if not (0 <= x0 <= x1 < width and 0 <= y0 <= y1 < height):
        raise ValueError("Crop rectangle outside the picture")
    return {"width": x1 - x0 + 1, "height": y1 - y0 + 1,
            "first_x": x0, "last_x": x1, "first_y": y0, "last_y": y1}


def pcm_luma(sample, sample_depth, bit_depth):
    if not 1 <= sample_depth <= bit_depth or not 0 <= sample < 2**sample_depth:
        raise ValueError("PCM sample or sample depth outside its range")
    return sample * 2**(bit_depth - sample_depth)


def active_ref_counts(p):
    if p["slice"] not in {"P", "B"}:
        raise ValueError("Fixture must use a P or B slice")
    lists = 2 if p["slice"] == "B" else 1
    capacities = p["entries"][:lists]
    present = any(size > 1 for size in capacities)
    override = p["override"]
    if (override is not None) != present or override not in (None, 0, 1):
        raise ValueError("Override flag presence contradicts the list sizes")
    override = 1 if override is None else override
    active, field_present = [0, 0], [0, 0]
    for i, capacity in enumerate(capacities):
        value = p["active_minus1"][i]
        field_present[i] = int(bool(override and capacity > 1))
        if (value is not None) != bool(field_present[i]):
            raise ValueError("Per-list syntax presence differs from override or capacity")
        active[i] = 1 + (0 if value is None else value) if override else min(capacity, 1 + p["defaults_minus1"][i])
        if not 1 <= active[i] <= capacity:
            raise ValueError("Active count outside the selected RPL")
    return {"override": override, "l0": active[0], "l1": active[1], "l0_field_present": field_present[0]}


def signed_distance(a, b, bits, enabled):
    if not enabled:
        return 0
    if not 1 <= bits <= 8 or not all(0 <= x < 2**bits for x in (a, b)):
        raise ValueError("Order hint outside its enabled range")
    period = 2**bits
    half = period // 2
    # Use modular arithmetic rather than duplicating the standard's bit masks.
    return (a - b + half) % period - half


def reference(case):
    p = case["inputs"]
    match case["codec"]:
        case "h264":
            def crop(offsets):
                return crop_rectangle(p["width"], p["height"], p["subsampling"], p["frame_only"], offsets)
            if "pair_offsets" in p:
                a, b = [crop(o) for o in p["pair_offsets"]]
                return {"a_width": a["width"], "a_height": a["height"], "b_width": b["width"], "b_height": b["height"]}
            return crop(p["offsets"] if p["enabled"] else None)
        case "h265":
            depth = p["bit_depth"]
            if "pair_pcm_minus1" in p:
                a, b = [x + 1 for x in p["pair_pcm_minus1"]]
                return {"a_depth": a, "a_pass": int(a <= depth), "b_depth": b, "b_pass": int(b <= depth)}
            pcm = p["pcm_minus1"] + 1
            if "samples" in p:
                first, second = [pcm_luma(s, pcm, depth) for s in p["samples"]]
                return {"shift": depth - pcm, "first": first, "second": second}
            return {"pcm_depth": pcm, "shift": depth - pcm, "sample": pcm_luma(p["sample"], pcm, depth)}
        case "h266":
            return active_ref_counts(p)
        case "av1":
            values = [signed_distance(a, b, p["bits"], p["enabled"]) for a, b in p["pairs"]]
            if len(values) == 2:
                return {"forward": values[0], "reverse": values[1]}
            return {"distance": values[0], "computes_mask": int(bool(p["enabled"]))}
        case _:
            raise ValueError("Unknown codec")


def verify():
    candidate_path = BATCH / "candidates.jsonl"
    fixtures = BATCH / "numeric-cases.json"
    earlier_paths = [ROOT / "datasets" / batch / "candidates.jsonl" for batch in ("pilot-v1", "validation-v1")]
    rows = read_jsonl(candidate_path)
    earlier = [r for path in earlier_paths for r in read_jsonl(path)]
    issues = validate(earlier + rows)
    if issues:
        raise ValueError("\n".join(issues))
    counts = Counter(r["codecs"][0] for r in rows)
    groups = {r["split_group"] for r in rows}
    if (counts != dict.fromkeys(CODECS, 3) or len(groups) != 4
            or groups.intersection(r["split_group"] for r in earlier)):
        raise ValueError("Expected three items and a separate mechanism per codec")
    cases = json.loads(fixtures.read_text())["cases"]
    if set(cases) != {r["id"] for r in rows}:
        raise ValueError("Numeric fixture coverage differs from candidate IDs")
    registry = read_split_registry()
    exclusions = load_dev_exclusions(registry)
    evidence, answers = set(), {}
    for row in rows:
        ident = row["id"]
        prompt, answer = [m["content"] for m in row["messages"]]
        if registered_split(row["split_group"], registry) != "train" or dev_overlap(
                exclusions, sample_id=ident, group=row["split_group"], prompt=prompt, evidence=row["evidence"]):
            raise ValueError(f"{ident}: overlaps or is reserved for evaluation")
        if row["verification"]["status"] != "pending" or row["eligibility"]["status"] != "pending":
            raise ValueError(f"{ident}: expected pending candidate")
        case = cases[ident]
        if row["codecs"] != [case["codec"]] or row["task_type"] != "calculation":
            raise ValueError(f"{ident}: invalid task or codec")
        expected = case["expected"]
        calculated = reference(case)
        result = {key: calculated[key] for key in expected}
        if (not expected or any(type(v) is not int for v in expected.values()) or result != expected
                or sha(prompt.encode()) != case["prompt_sha256"] or numeric_result(answer, expected) != "correct"):
            raise ValueError(f"{ident}: prompt or answer differs from numeric fixture")
        evidence.update(evidence_fingerprint(ev) for ev in row["evidence"])
        answers[ident] = result
    return {"batch": "boundary-v1", "status": "checked_pending_domain_review", "approved": 0,
            "candidates_sha256": file_sha(candidate_path), "numeric_cases_sha256": file_sha(fixtures),
            "earlier_candidates_sha256": {str(p.relative_to(ROOT)): file_sha(p) for p in earlier_paths},
            "codec_counts": dict(counts), "groups": sorted(groups),
            "evidence_locators_verified": len(evidence), "numeric_answers": answers}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()
    result = verify()
    report = BATCH / "verification-report.json"
    if args.write_report:
        write_json(report, result)
    elif json.loads(report.read_text()) != result:
        parser.error("Verification report differs from the recorded snapshot")
    print(f"Verified {len(result['numeric_answers'])} numeric answers and "
          f"{result['evidence_locators_verified']} locked source locations; approval pending.")


if __name__ == "__main__":
    main()
