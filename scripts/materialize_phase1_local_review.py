#!/usr/bin/env python3
"""Materialize the recorded, scope-limited AI review without changing candidates."""
import argparse
import json
from pathlib import Path

from avllm_data import ROOT, read_jsonl, sha, validate

REVIEW = ROOT / "datasets/pilot-v1/m4pro-local-review.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if ROOT / "data/approved" not in output.parents or output.exists():
        parser.error("Use a new file under data/approved/")
    review = json.loads(REVIEW.read_text())
    if review["scope"] != "local_m4pro_domain_smoke" or review["reviewer_kind"] != "AI":
        parser.error("Review does not grant this local smoke scope")
    rows = {}
    for batch in ("pilot-v1", "validation-v1"):
        path = ROOT / "datasets" / batch / "candidates.jsonl"
        if sha(path.read_bytes()) != review["candidate_batch_sha256"][batch]:
            parser.error(f"Candidate batch changed: {batch}")
        rows.update({row["id"]: row for row in read_jsonl(path)})
    expected = {ident for ident, row in rows.items() if row["task_type"] in {"calculation", "source_code"}}
    if {entry["id"] for entry in review["items"]} != expected or len(review["items"]) != len(expected):
        parser.error("Review IDs do not match the calculation and source-code candidates")
    result = []
    for item in review["items"]:
        if item["decision"] != "pass_local_smoke":
            continue
        row = rows[item["id"]]
        if "answer_revision" in item:
            row["messages"][-1]["content"] = item["answer_revision"]
        kinds = ["evidence", "conditions", "calculation" if row["task_type"] == "calculation" else "code"]
        row["verification"] = {
            "status": "passed", "reviewer": review["reviewer"], "reviewed_at": review["reviewed_at"],
            "checks": [{"kind": kind, "result": "passed", "artifact": str(REVIEW.relative_to(ROOT))} for kind in kinds],
        }
        row["eligibility"] = {"status": "approved", "note": review["use_scope_note"]}
        result.append(row)
    errors = validate(result, require_approved=True)
    if errors:
        parser.error("\n".join(errors))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        for row in result:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Wrote {len(result)} reviewed samples for the local smoke run.")


if __name__ == "__main__":
    main()
