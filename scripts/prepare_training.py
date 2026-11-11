#!/usr/bin/env python3
"""Fail-closed export of reviewed samples, with deterministic group isolation."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from avllm_data import ROOT, read_jsonl, sha, split_for, validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    rows = read_jsonl(args.path)
    errors = validate(rows, require_approved=True, root=ROOT)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    holdout_path = ROOT / "configs/holdout-groups.json"
    holds = json.loads(holdout_path.read_text())["groups"]
    splits = {k: [] for k in ["train", "valid", "test"]}
    for row in rows:
        splits[split_for(row["split_group"], holds)].append(row)
    if not splits["train"] or not splits["valid"]:
        parser.error("Train and valid must both be nonempty; collect more independent groups, do not move paraphrases across groups")
    output = Path(args.output)
    if output.exists() and any(output.iterdir()):
        parser.error("Output directory is nonempty; use a versioned output directory")
    output.mkdir(parents=True, exist_ok=True)
    metadata = {"schema_version": 1, "source_dataset_sha256": sha(Path(args.path).read_bytes()),
                "source_lock_sha256": sha((ROOT / "materials/sources.lock.json").read_bytes()),
                "holdout_registry_sha256": sha(holdout_path.read_bytes()), "splits": {}}
    artifacts = {check["artifact"] for row in rows for check in row["verification"]["checks"]}
    metadata["verification_artifact_sha256"] = {p: sha((ROOT / p).read_bytes()) for p in sorted(artifacts)}
    provenance = []
    for split, items in splits.items():
        out = output / f"{split}.jsonl"
        out.write_text("".join(json.dumps({"messages": row["messages"]}, ensure_ascii=False) + "\n" for row in items))
        metadata["splits"][split] = {"samples": len(items), "groups": len({x["split_group"] for x in items}),
                                     "sha256": sha(out.read_bytes()),
                                     "codec_counts": dict(Counter(c for x in items for c in x["codecs"]))}
        provenance.extend({"split": split, "line": i, "sample": x} for i, x in enumerate(items, 1))
    (output / "provenance.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in provenance))
    metadata["provenance_sha256"] = sha((output / "provenance.jsonl").read_bytes())
    (output / "manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    if not holds:
        print("Note: no registered frozen holdout groups yet; deterministic test split is not a completed independent benchmark.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
