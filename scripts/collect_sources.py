#!/usr/bin/env python3
"""Collect declared sources without executing third-party code; record actual outcomes."""
import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run(cmd, timeout=180):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          env=env, check=True).stdout.strip()


def collect(source, old, refresh):
    path = (ROOT / source["path"]).resolve()
    if ROOT not in path.parents:
        raise ValueError("Source path escapes repository")
    record = {k: source[k] for k in ("id", "codec", "kind", "title", "version", "url", "path", "role", "rights")}
    record.update(checked_at=stamp(), training_eligibility="pending_review")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if source["kind"] == "git":
            if path.exists() and not (path / ".git").exists():
                raise ValueError("Existing target is not a Git checkout")
            if not path.exists():
                urls = [source["url"]] + source.get("fallback_urls", [])
                errors = []
                for url in urls:
                    staging = Path(tempfile.mkdtemp(prefix=path.name + "-", dir=path.parent))
                    try:
                        cmd = ["git", "clone", "--depth", "1", "--single-branch", "--no-tags"]
                        if source.get("ref") and not old.get("commit"):
                            cmd += ["--branch", source["ref"]]
                        cmd += [url, str(staging)]
                        run(cmd)
                        if old.get("commit") and not refresh:
                            run(["git", "-C", str(staging), "fetch", "--depth", "1", "origin", old["commit"]])
                            run(["git", "-C", str(staging), "checkout", "--detach", "FETCH_HEAD"])
                        staging.rename(path)
                        break
                    except Exception as e:
                        errors.append(f"{url}: {str(e)[:350]}")
                        shutil.rmtree(staging)
                else:
                    raise RuntimeError("; ".join(errors))
            if refresh:
                raise ValueError("Git refresh is deliberately manual: add a new source/version instead of moving a pinned checkout")
            commit = run(["git", "-C", str(path), "rev-parse", "HEAD"])
            if old.get("commit") and commit != old["commit"]:
                raise ValueError("Checkout differs from locked commit")
            dirty = run(["git", "-C", str(path), "status", "--porcelain"])
            if dirty:
                raise ValueError("Third-party checkout has local changes")
            record.update(commit=commit, resolved_url=run(["git", "-C", str(path), "remote", "get-url", "origin"]),
                          status="collected", bytes=sum(p.stat().st_size for p in path.rglob("*") if p.is_file()))
            record["license_files"] = [str(p.relative_to(ROOT)) for p in path.iterdir()
                                       if p.is_file() and any(t in p.name.lower() for t in ("license", "copying", "patent", "copyright"))]
        else:
            if not path.exists() or refresh:
                part = path.with_suffix(path.suffix + ".part")
                try:
                    # TLS verification stays enabled. PDF signatures also catch HTML login/error pages.
                    run(["curl", "--fail", "--location", "--silent", "--show-error", "--retry", "1",
                         "--max-time", "90", "--user-agent", "AVllm-materials/0.1",
                         "--output", str(part), source["url"]], timeout=200)
                    header = part.open("rb").read(1024)
                    if source["kind"] == "pdf" and b"%PDF-" not in header:
                        raise ValueError("Expected PDF, received another format")
                    if source["kind"] == "archive" and not zipfile.is_zipfile(part):
                        raise ValueError("Expected ZIP archive")
                    if part.stat().st_size < 50:
                        raise ValueError("Downloaded content unexpectedly short")
                    if source["kind"] == "html" and b"<html" not in header.lower() and b"<!doctype" not in header.lower():
                        raise ValueError("Expected HTML page")
                    if old.get("sha256") and not refresh and digest(part) != old["sha256"]:
                        raise ValueError("Upstream bytes changed from lock; inspect and explicitly version the source")
                    part.replace(path)
                finally:
                    part.unlink(missing_ok=True)
            sha = digest(path)
            if old.get("sha256") and not refresh and sha != old["sha256"]:
                raise ValueError("Local file differs from locked SHA-256")
            # Keep the public download URL; redirected asset links can carry short-lived signatures.
            record.update(status="collected", sha256=sha, bytes=path.stat().st_size,
                          resolved_url=source["url"])
        record["collected_at"] = old.get("collected_at", stamp())
    except Exception as exc:
        record.update(status="unavailable", error=str(exc)[:1500])
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-code", action="store_true")
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--refresh", action="store_true", help="Explicitly replace HTTP snapshots; Git is never advanced")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    sources = json.loads((ROOT / "configs/sources.json").read_text())["sources"]
    lock_path = ROOT / "materials/sources.lock.json"
    old_lock = json.loads(lock_path.read_text()) if lock_path.exists() else {"sources": []}
    old = {s["id"]: s for s in old_lock["sources"]}
    selected = [s for s in sources if (args.include_code or s["kind"] != "git") and
                (args.only is None or s["id"] in args.only)]
    if args.only and set(args.only) - {s["id"] for s in selected}:
        parser.error("Unknown or excluded source id; Git sources also require --include-code")
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(collect, s, old.get(s["id"], {}), args.refresh) for s in selected]
        for future in concurrent.futures.as_completed(futures):
            item = future.result()
            old[item["id"]] = item
            print(f"{item['status']:12} {item['id']}" + (": " + item.get("error", "")[:180] if item["status"] != "collected" else ""), flush=True)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    result = {"schema_version": 1, "updated_at": stamp(), "sources": [old[s["id"]] for s in sources if s["id"] in old]}
    lock_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    lines = ["# 本地资料盘点", "", f"生成时间（UTC）：{result['updated_at']}", "",
             "此文件由 `python3 scripts/collect_sources.py --include-code` 生成。下载成功不代表已获准训练或再分发；审核结果另见数据样本的 eligibility。", ""]
    for item in result["sources"]:
        lines += [f"## {item['id']} · {item['status']}", "", f"- 标题：{item['title']}", f"- 类型 / 用途：{item['kind']} / {item['role']}",
                  f"- 来源：{item.get('resolved_url', item['url'])}", f"- 本地路径：`{item['path']}`", f"- 声明版本：{item['version']}"]
        for key in ("commit", "sha256", "bytes", "error"):
            if key in item:
                lines.append(f"- {key}：{item[key]}")
        lines += [f"- 使用条件：{item['rights']}", ""]
    (ROOT / "materials/INVENTORY.md").write_text("\n".join(lines))
    failed = [s for s in result["sources"] if s["id"] in {x["id"] for x in selected} and s["status"] != "collected"]
    print(f"Completed {len(selected)} selected sources; {len(failed)} unavailable.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
