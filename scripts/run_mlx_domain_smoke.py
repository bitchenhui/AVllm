#!/usr/bin/env python3
"""Train a local LoRA and compare the same masked validation set after reload."""
import argparse
import gc
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import time
from types import SimpleNamespace

from avllm_data import ROOT, read_jsonl
from dev_benchmark import file_sha, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    output = options.output.resolve()
    if ROOT / "runs" not in output.parents or output.exists():
        parser.error("Use a new local directory under runs/")
    config = json.loads(options.config.read_text())
    model_dir, data = (ROOT / config["model"]).resolve(), (ROOT / config["data"]).resolve()
    receipt = json.loads((model_dir / "avllm-model-revision.json").read_text())
    if file_sha(model_dir / "model.safetensors") != receipt["weight_sha256"]:
        parser.error("Model weights differ from the recorded local receipt")
    manifest = json.loads((data / "manifest.json").read_text())
    provenance = data / "provenance.jsonl"
    if file_sha(provenance) != manifest["provenance_sha256"]:
        parser.error("Export provenance changed")
    provenance_rows = read_jsonl(provenance)
    rows = {}
    for split in ("train", "valid"):
        path = data / f"{split}.jsonl"
        if file_sha(path) != manifest["splits"][split]["sha256"]:
            parser.error(f"Exported {split} data changed")
        rows[split] = read_jsonl(path)
        backed = [r["sample"] for r in provenance_rows if r["split"] == split]
        if ([r["messages"] for r in backed] != [r["messages"] for r in rows[split]]
                or any(r["verification"]["status"] != "passed" or r["eligibility"]["status"] != "approved" for r in backed)):
            parser.error(f"Exported {split} rows must match reviewed provenance")
    valid_ids = [r["sample"]["id"] for r in provenance_rows if r["split"] == "valid"]
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    import mlx.core as mx
    import numpy as np
    from mlx_lm import load
    from mlx_lm.lora import CONFIG_DEFAULTS, train_model
    from mlx_lm.tuner.callbacks import TrainingCallback
    from mlx_lm.tuner.datasets import ChatDataset
    from mlx_lm.tuner.trainer import default_loss

    args = SimpleNamespace(**{**CONFIG_DEFAULTS, **config, "model": str(model_dir), "data": str(data),
                              "adapter_path": str(output / "adapter")})
    if args.fine_tune_type != "lora" or not args.mask_prompt or args.test or args.resume_adapter_file:
        parser.error("Expected fresh LoRA with prompt masking and no test split")
    output.mkdir(parents=True, exist_ok=False)
    events = []

    class LocalMetrics(TrainingCallback):
        def add(self, kind, info):
            event = {"kind": kind, **info}
            events.append(event)
            with (output / "metrics.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, allow_nan=False) + "\n")

        def on_train_loss_report(self, train_info):
            self.add("train", train_info)

        def on_val_loss_report(self, val_info):
            self.add("valid_before_iteration", val_info)

    def evaluate(model, valid):
        model.eval()
        samples = []
        for ident, row in zip(valid_ids, rows["valid"]):
            tokens, offset = valid.process(row)
            loss, count = default_loss(model, mx.array([tokens]), mx.array([[offset, len(tokens)]]))
            values = {"id": ident, "loss": float(loss.item()), "answer_tokens": int(count.item())}
            if not math.isfinite(values["loss"]) or values["answer_tokens"] < 1:
                raise ValueError(f"{ident}: invalid validation loss")
            samples.append(values)
        total = sum(r["answer_tokens"] for r in samples)
        return {"loss": sum(r["loss"] * r["answer_tokens"] for r in samples) / total,
                "answer_tokens": total, "items": samples}

    model, tokenizer = load(str(model_dir))
    datasets = {split: ChatDataset(items, tokenizer, mask_prompt=True) for split, items in rows.items()}
    lengths = {}
    for split, dataset in datasets.items():
        batches = [dataset.process(r) for r in rows[split]]
        if any(not 0 < offset < len(tokens) <= args.max_seq_length for tokens, offset in batches):
            parser.error(f"{split}: sample would be truncated or has an empty masked answer")
        lengths[split] = {"samples": len(batches), "max_sequence_tokens": max(len(tokens) for tokens, _ in batches)}
    before = evaluate(model, datasets["valid"])
    print(f"Base validation loss: {before['loss']:.6f}", flush=True)
    write_json(output / "base-validation.json", before)
    mx.clear_cache()
    mx.reset_peak_memory()
    np.random.seed(args.seed)
    layer_type = type(model.layers[-1])
    original_call = layer_type.__call__
    start = time.perf_counter()
    try:
        train_model(args, model, datasets["train"], datasets["valid"], LocalMetrics())
    finally:
        layer_type.__call__ = original_call
    elapsed = round(time.perf_counter() - start, 4)
    peak = mx.get_peak_memory()
    del model
    gc.collect()
    mx.clear_cache()
    adapter = output / "adapter" / "adapters.safetensors"
    tensors = mx.load(str(adapter))
    b = [value for key, value in tensors.items() if key.endswith(".lora_b")]
    updated = sum(bool(mx.any(value != 0).item()) for value in b)
    if not updated or not all(mx.all(mx.isfinite(value)).item() for value in tensors.values()):
        parser.error("Saved adapter tensors are non-finite or did not update")
    tuned, _ = load(str(model_dir), adapter_path=args.adapter_path)
    after = evaluate(tuned, datasets["valid"])
    if before["answer_tokens"] != after["answer_tokens"]:
        raise ValueError("Validation token counts changed")
    record = {"status": "completed", "scope": "local_m4pro_domain_smoke", "model": receipt,
              "platform": platform.platform(), "chip": subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip(),
              "mlx_lm_version": importlib.metadata.version("mlx-lm"), "mlx_version": importlib.metadata.version("mlx"),
              "config": config, "config_sha256": file_sha(options.config), "dataset": manifest,
              "lengths": lengths, "train_seconds_includes_inline_validation": elapsed, "mlx_training_peak_bytes": peak,
              "adapter_sha256": file_sha(adapter), "adapter_tensors": len(tensors), "nonzero_lora_b_matrices": updated,
              "base_validation": before, "reloaded_adapter_validation": after, "metrics": events,
              "limits": "Four validation items; teacher-forced masked answer loss only, no final benchmark used."}
    write_json(output / "manifest.json", record)
    print(f"Reloaded adapter validation loss: {after['loss']:.6f}; MLX peak {peak / 1e9:.2f} GB", flush=True)


if __name__ == "__main__":
    main()
