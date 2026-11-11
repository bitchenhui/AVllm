#!/usr/bin/env python3
"""Validate candidate provenance, or require reviewed samples for training export."""
import argparse
import sys
from avllm_data import read_jsonl, validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    parser.add_argument("--require-approved", action="store_true")
    args = parser.parse_args()
    try:
        rows = read_jsonl(args.path)
        errors = validate(rows, args.require_approved)
    except (OSError, ValueError) as exc:
        errors = [str(exc)]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Validated {len(rows)} samples. Provenance checks are not a proof of factual correctness.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
