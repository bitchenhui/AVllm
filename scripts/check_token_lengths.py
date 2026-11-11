#!/usr/bin/env python3
"""Check complete chat-template lengths with a local tokenizer before training."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import sys
from avllm_data import read_jsonl, sha


def message_lengths(tokenizer, items):
    lengths = []
    for row in items:
        tokens = tokenizer.apply_chat_template(
            row["messages"], tokenize=True, add_generation_prompt=False, return_dict=False,
        )
        if not isinstance(tokens, list) or not tokens or any(type(t) is not int for t in tokens):
            raise ValueError("Expected a nonempty flat list of token IDs from the chat template")
        lengths.append(len(tokens))
    return lengths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset")
    parser.add_argument("--tokenizer", required=True, help="Existing local model/tokenizer directory")
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    if args.max_tokens < 1:
        parser.error("max-tokens must be positive")
    model = Path(args.tokenizer)
    if not model.is_dir():
        parser.error("Tokenizer must be a local directory; this script does not download weights or tokenizers")
    try:
        from transformers import AutoTokenizer
    except ImportError:
        parser.error("Run in the training environment with transformers installed")
    tokenizer = AutoTokenizer.from_pretrained(str(model), local_files_only=True)
    items = read_jsonl(args.dataset)
    try:
        lengths = message_lengths(tokenizer, items)
    except ValueError as exc:
        parser.error(str(exc))
    violations = [{"line": i + 1, "tokens": n} for i, n in enumerate(lengths) if n > args.max_tokens]
    report = {"report_version": 2, "transformers_version": importlib.metadata.version("transformers"),
              "chat_template_options": {"tokenize": True, "add_generation_prompt": False, "return_dict": False},
              "dataset": args.dataset, "dataset_sha256": sha(Path(args.dataset).read_bytes()),
              "samples": len(items), "total_tokens": sum(lengths), "max_tokens": max(lengths),
              "configured_limit": args.max_tokens, "over_limit": violations,
              "per_sample": [{"line": i + 1, "id": row.get("id"), "tokens": n}
                             for i, (row, n) in enumerate(zip(items, lengths))],
              "tokenizer_files": {str(p.relative_to(model)):sha(p.read_bytes()) for p in model.iterdir()
                                  if p.is_file() and ("tokenizer" in p.name or "chat_template" in p.name or p.name == "config.json")}}
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"Checked {len(items)} samples; maximum {max(lengths)} tokens; over limit {len(violations)}")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
