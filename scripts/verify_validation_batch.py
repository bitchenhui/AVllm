#!/usr/bin/env python3
"""Check independent validation candidates against locked sources and integer oracles."""
import argparse
from collections import Counter
from itertools import accumulate
import json

from avllm_data import (
    ROOT, dev_overlap, evidence_fingerprint, load_dev_exclusions, read_jsonl,
    read_split_registry, registered_split, sha, validate,
)
from dev_benchmark import numeric_result

BATCH = ROOT / "datasets/validation-v1"
REPORT = BATCH / "verification-report.json"


def reference(case):
    p = case["inputs"]
    name = case["operation"]
    if name == "avc_horizontal_luma":
        e, f, g, h, i, j = p["samples"]
        maximum = 2 ** p["bit_depth_y"] - 1
        if any(not 0 <= v <= maximum for v in p["samples"]):
            raise ValueError("Out-of-range luma sample")
        # Symmetric tap pairs; keep the unclipped intermediate separate.
        raw = (e + j) - 5 * (f + i) + 20 * (g + h)
        rounded, fraction = divmod(raw, 32)
        half = max(0, min(maximum, rounded + (fraction >= 16)))
        return {"half_b": half, "quarter_a": -(-(g + half) // 2)}
    if name == "hevc_tile_order":
        cols, rows = p["col_widths"], p["row_heights"]
        if min(cols + rows) < 1:
            raise ValueError("Empty CTB tile")
        xbounds, ybounds = [0, *accumulate(cols)], [0, *accumulate(rows)]
        raster_at_ts = [y * xbounds[-1] + x
                        for y0, y1 in zip(ybounds, ybounds[1:])
                        for x0, x1 in zip(xbounds, xbounds[1:])
                        for y in range(y0, y1) for x in range(x0, x1)]
        return {"ts_for_rs": raster_at_ts.index(p["rs"]), "rs_for_ts": raster_at_ts[p["ts"]]}
    if name == "vvc_independent_subpic":
        if p != {"independent": 1}:
            raise ValueError("Fixture only covers the absent-flags branch")
        return {"treated_as_pic": 1, "cross_loop_filter": 0}
    if name == "av1_grain_reuse":
        if any(not 0 <= seed < 65536 for seed in p.values()):
            raise ValueError("Grain seed outside 16-bit range")
        inherited = {"grain_seed": p["reference_seed"]}
        inherited["grain_seed"] = p["current_seed"]
        return inherited
    raise ValueError(f"Unknown validation case: {name}")


def verify():
    train_path = ROOT / "datasets/pilot-v1/candidates.jsonl"
    val_path = BATCH / "candidates.jsonl"
    fixture_path = BATCH / "numeric-cases.json"
    training, validation = read_jsonl(train_path), read_jsonl(val_path)
    issues = validate(training + validation)
    if issues:
        raise ValueError("\n".join(issues))
    registry = read_split_registry()
    exclusions = load_dev_exclusions(registry)
    cases = json.loads(fixture_path.read_text())["cases"]
    if set(cases) != {r["id"] for r in validation if r["task_type"] == "calculation"}:
        raise ValueError("Wrong numeric fixture coverage")

    training_groups = {r["split_group"] for r in training}
    validation_groups = {r["split_group"] for r in validation}
    if validation_groups.intersection(training_groups) or not validation_groups.issubset(registry["validation_groups"]):
        raise ValueError("Validation groups overlap training or were not reserved")
    if any(registered_split(r["split_group"], registry) != "train" for r in training):
        raise ValueError("Pilot training groups changed split")
    evidence = set()
    outputs = {}
    for row in validation:
        ident = row["id"]
        prompt, answer = [m["content"] for m in row["messages"]]
        if dev_overlap(exclusions, sample_id=ident, group=row["split_group"], prompt=prompt, evidence=row["evidence"]):
            raise ValueError(f"{ident}: overlaps development benchmark")
        if row["verification"]["status"] != "pending" or row["eligibility"]["status"] != "pending":
            raise ValueError(f"{ident}: not a pending validation candidate")
        evidence.update(evidence_fingerprint(ev) for ev in row["evidence"])
        if ident in cases:
            case = cases[ident]
            expected = reference(case)
            if (sha(prompt.encode()) != case["prompt_sha256"] or expected != case["expected"]
                    or numeric_result(answer, expected) != "correct"):
                raise ValueError(f"{ident}: prompt or answer differs from verified fixture")
            outputs[ident] = expected
    counts = Counter(r["codecs"][0] for r in validation)
    if counts != dict.fromkeys(("h264", "h265", "h266", "av1"), 2):
        raise ValueError("Expected two validation candidates per codec")
    return {"batch": "validation-v1", "status": "checked_pending_domain_approval",
            "candidates_sha256": sha(val_path.read_bytes()), "numeric_cases_sha256": sha(fixture_path.read_bytes()),
            "training_pilot_sha256": sha(train_path.read_bytes()),
            "codec_counts": dict(counts), "validation_groups": sorted(validation_groups),
            "locked_locators_checked": len(evidence), "numeric_answers": outputs,
            "training_or_development_overlaps": 0, "approved": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()
    try:
        result = verify()
        if args.write_report:
            REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        elif json.loads(REPORT.read_text()) != result:
            raise ValueError("Recorded validation report differs")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"{exc}\n")
    print(f"Checked {sum(result['codec_counts'].values())} validation candidates, "
          f"{len(result['numeric_answers'])} numeric answers, {result['locked_locators_checked']} locators; "
          "no overlap with pilot training or dev; approval pending")


if __name__ == "__main__":
    main()
