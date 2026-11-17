#!/usr/bin/env python3
"""Create an anonymized scoring queue and aggregate ratings after grading."""
import argparse
from collections import Counter
import json
from pathlib import Path
import secrets

from avllm_data import read_jsonl, sha
from dev_benchmark import file_sha, index, load_key, load_questions


def write_rows(path, rows):
    with path.open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def prepare(benchmark, runs, output):
    manifest, questions = load_questions(benchmark)
    keys = load_key(manifest, questions, benchmark)
    predictions = {}
    for run in runs:
        recorded = json.loads((run / "manifest.json").read_text())
        file = run / "predictions.jsonl"
        if (recorded["status"] != "completed" or recorded["questions_sha256"] != manifest["questions_sha256"]
                or file_sha(file) != recorded["predictions_sha256"]):
            raise ValueError(f"Invalid or mismatched run: {run}")
        predictions[run.name] = index(read_jsonl(file), run.name)
        if predictions[run.name].keys() != questions.keys():
            raise ValueError(f"Question IDs differ: {run}")
    rng = secrets.SystemRandom()
    queue, identities = [], []
    for qid, question in questions.items():
        if keys[qid]["numeric"] is not None:
            continue
        order = list(predictions)
        rng.shuffle(order)
        entries = []
        for tag, run in zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", order):
            answer = predictions[run][qid]["answer"]
            entries.append((tag, answer))
            identities.append({"id": qid, "label": tag, "run": run, "answer_sha256": sha(answer.encode())})
        queue.append({"id": qid, "prompt": question["prompt"], "rubric": keys[qid]["rubric"],
                      "reference": keys[qid]["reference_answer"], "answers": dict(entries)})
    output.mkdir(parents=True, exist_ok=False)
    write_rows(output / "queue.jsonl", queue)
    write_rows(output / "private-identities.jsonl", identities)


def aggregate(queue, identities, ratings):
    prompts = index(queue, "queue")
    mapping = {(x["id"], x["label"]): x for x in identities}
    wanted = {(q["id"], label) for q in queue for label in q["answers"]}
    if len(mapping) != len(identities) or set(mapping) != wanted:
        raise ValueError("Identities do not match the complete anonymous queue")
    seen, totals, result = set(), {}, []
    for r in ratings:
        q = prompts[r["id"]]
        k = (r["id"], r["label"])
        if k in seen or k not in mapping:
            raise ValueError("Duplicate or unknown review label")
        seen.add(k)
        points = {p["id"] for p in q["rubric"]}
        answer = q["answers"][r["label"]]
        if (set(r["points"]) != points or any(type(x) is not int or x not in (0, 1) for x in r["points"].values())
                or not r["note"].strip() or mapping[k]["answer_sha256"] != sha(answer.encode())):
            raise ValueError("Invalid rating, note, or answer hash")
        run = mapping[k]["run"]
        ctx = totals.setdefault(run, Counter())
        ctx.update(points=sum(r["points"].values()), possible=len(points), answers=1,
                   all_points=int(sum(r["points"].values()) == len(points)))
        result.append({**r, "run": run, "answer_sha256": mapping[k]["answer_sha256"]})
    if seen != set(mapping):
        raise ValueError("Review does not cover all answers")
    return {"totals": {run: dict(v) for run, v in sorted(totals.items())}, "items": result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="step", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--benchmark", type=Path, required=True)
    p.add_argument("--runs", type=Path, nargs="+", required=True)
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("aggregate")
    p.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    if args.step == "prepare":
        if not 2 <= len(args.runs) <= 26 or len({r.name for r in args.runs}) != len(args.runs):
            parser.error("Expected distinct names for 2–26 runs")
        prepare(args.benchmark, args.runs, args.output)
    else:
        d = args.directory
        print(json.dumps(aggregate(*(read_jsonl(d / p) for p in ("queue.jsonl", "private-identities.jsonl", "ratings.jsonl"))),
                         ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
