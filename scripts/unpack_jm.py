#!/usr/bin/env python3
"""Safely unpack the locked JM archive for browsing; never execute its contents."""
import json
from pathlib import Path
import shutil
import stat
import zipfile
from avllm_data import ROOT, bounded_path, sha


def main():
    sources = json.loads((ROOT / "materials/sources.lock.json").read_text())["sources"]
    source = next(x for x in sources if x["id"] == "jm-code")
    path = ROOT / source["path"]
    if source.get("status") != "collected" or sha(path.read_bytes()) != source["sha256"]:
        raise ValueError("JM archive missing or changed")
    target = ROOT / "materials/code/JM"
    if target.exists():
        marker = target / ".avllm-archive-sha256"
        if marker.is_file() and marker.read_text().strip() == source["sha256"]:
            print("JM already unpacked from the locked archive")
            return
        raise ValueError("Existing JM directory is not marked as this locked archive")
    with zipfile.ZipFile(path) as archive:
        # Validate all destinations before writing. Reject symlinks and zip bombs.
        if sum(x.file_size for x in archive.infolist()) > 256 * 1024 * 1024:
            raise ValueError("Unexpectedly large reference archive")
        for item in archive.infolist():
            if not item.filename.startswith("JM/") or stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError("Unexpected archive member")
            bounded_path(ROOT / "materials/code", item.filename)
        target.mkdir(parents=True)
        for item in archive.infolist():
            relative = item.filename.removeprefix("JM/")
            if not relative:
                continue
            destination = bounded_path(target, relative)
            if item.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as src, destination.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
    (target / ".avllm-archive-sha256").write_text(source["sha256"] + "\n")
    print(f"Unpacked {target} (reference archive only; no build executed)")


if __name__ == "__main__":
    main()
