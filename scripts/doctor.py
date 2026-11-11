#!/usr/bin/env python3
"""Report hardware and optional dependencies without installing anything."""
import importlib.metadata
import json
import platform
import shutil
import subprocess


def command(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, check=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


result = {"os": platform.platform(), "arch": platform.machine(), "python": platform.python_version()}
if platform.system() == "Darwin":
    result.update(chip=command(["sysctl", "-n", "machdep.cpu.brand_string"]), memory_bytes=command(["sysctl", "-n", "hw.memsize"]))
result["nvidia_smi"] = command(["nvidia-smi", "--query-gpu=name,memory.total,power.limit,driver_version", "--format=csv,noheader"])
result["tools"] = {x: shutil.which(x) for x in ["git", "curl", "ffmpeg", "ffprobe", "uv", "mlx_lm.lora"]}
result["packages"] = {}
for name in ["mlx", "mlx-lm", "transformers", "torch", "pypdf"]:
    try:
        result["packages"][name] = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        result["packages"][name] = None
print(json.dumps(result, ensure_ascii=False, indent=2))
