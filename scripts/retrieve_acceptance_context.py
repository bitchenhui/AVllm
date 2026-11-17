#!/usr/bin/env python3
"""Deterministic search over locked local standard pages, using question text only."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re

from avllm_data import ROOT, read_jsonl, sha
from dev_benchmark import file_sha, load_questions, write_json
from verify_acceptance import LOCK, PRIVATE

SOURCES = {"h264": "h264-spec", "h265": "h265-spec", "h266": "h266-spec", "av1": "av1-spec-pdf"}
COMMON = {"the", "is", "of", "to", "and", "for", "a", "in", "v", "h", "s"}


def terms(text):
    words = re.findall(r"[a-z][a-z0-9_]*", text.lower())
    result = []
    for word in words:
        if word not in COMMON:
            result.append(word)
        if "_" in word:
            result.extend(part for part in word.split("_") if len(part) > 2 and part not in COMMON)
    return result


def catalog(source):
    if file_sha(ROOT / source["path"]) != source["sha256"]:
        raise ValueError("Standard PDF changed")
    directory = ROOT / "materials/extracted" / source["id"]
    if json.loads((directory / "metadata.json").read_text())["source_sha256"] != source["sha256"]:
        raise ValueError("Stale PDF extraction")
    file = directory / "pages.jsonl"
    chunks = []
    for row in read_jsonl(file):
        if sha(row["text"].encode()) != row["text_sha256"]:
            raise ValueError("Page text hash mismatch")
        lines = row["text"].splitlines()
        for start in range(0, len(lines), 15):
            selected = lines[start:start + 27]
            if len(selected) < 5:
                continue
            body = "\n".join(selected)
            tf = Counter(terms(body))
            if tf:
                chunks.append((row["pdf_page"], start + 1, start + len(selected), body, tf, sum(tf.values())))
    return chunks, file_sha(file)


def search(chunks, question, limit=4):
    query = Counter(terms(question))
    df = Counter(t for _, _, _, _, words, _ in chunks for t in words.keys() & query.keys())
    avg_len = sum(chunk[5] for chunk in chunks) / len(chunks)
    rank = []
    for p, start, end, text, tf, length in chunks:
        score = sum(math.log1p((len(chunks) - df[t] + .5) / (df[t] + .5))
                    * (tf[t] * 2.2) / (tf[t] + 1.2 * (.25 + .75 * length / avg_len))
                    * (1 + math.log(n)) for t, n in query.items() if t in tf)
        if score:
            rank.append((score, p, start, end, text))
    selected = []
    for _, page, start, end, text in sorted(rank, key=lambda x: (-x[0], x[1], x[2])):
        if any(page == p and max(start, a) <= min(end, b) for p, a, b, _ in selected):
            continue
        selected.append((page, start, end, text))
        if len(selected) >= limit:
            break
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    manifest, questions = load_questions(PRIVATE)
    if manifest != json.loads(LOCK.read_text()):
        parser.error("Question manifest is not frozen")
    lock = ROOT / "materials/sources.lock.json"
    sources = {s["id"]: s for s in json.loads(lock.read_text())["sources"]}
    catalogs = {c: catalog(sources[s]) for c, s in SOURCES.items()}
    contexts, items = [], {}
    for ident, q in questions.items():
        codec = q["codec"]
        chosen = search(catalogs[codec][0], q["prompt"])
        contexts.append({"id": ident, "context": "\n\n".join(
            f"{sources[SOURCES[codec]]['title']} · PDF {page} · extracted lines {start}–{end}\n{text}"
            for page, start, end, text in chosen)})
        items[ident] = [{"page": p, "start": s, "end": e, "sha256": sha(t.encode())} for p, s, e, t in chosen]
    args.output.mkdir(parents=True, exist_ok=False)
    file = args.output / "contexts.jsonl"
    file.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in contexts), encoding="utf-8")
    write_json(args.output / "manifest.json", {
        "method": "codec-routed BM25 over all locked PDF page text; 27 extracted lines, stride 15, top 4 non-overlapping",
        "questions_sha256": manifest["questions_sha256"], "contexts_sha256": file_sha(file),
        "source_lock_sha256": file_sha(lock), "extraction_sha256": {SOURCES[c]: d for c, (_, d) in catalogs.items()}, "items": items})


if __name__ == "__main__":
    main()
