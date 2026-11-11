#!/usr/bin/env python3
"""Separate numeric content from strict output formatting without changing benchmark scores."""
import argparse
import json
from pathlib import Path
import re

from avllm_data import read_jsonl
from dev_benchmark import file_sha, index, load_key, load_questions, numeric_result, reference_numeric, unique_json_fields


def content_result(answer, expected):
    strict = numeric_result(answer, expected)
    if strict != 'unparseable':
        return strict
    candidate = answer.strip()
    fence = re.search(r'(?:^|\n)```(?:json)?[ \t]*\n(.*?)\n```\s*$', candidate, re.S)
    if fence:
        candidate = fence.group(1).strip()
    try:
        parsed = json.loads(candidate, object_pairs_hook=unique_json_fields)
    except ValueError:
        return 'unparseable'
    if not isinstance(parsed, dict) or set(parsed) != set(expected) or any(type(v) is not int for v in parsed.values()):
        return 'unparseable'
    return 'correct' if parsed == expected else 'incorrect'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest, questions = load_questions()
    keys = load_key(manifest, questions)
    run = json.loads((args.run_dir / 'manifest.json').read_text())
    predictions = args.run_dir / 'predictions.jsonl'
    if (run['status'] != 'completed' or run['questions_sha256'] != manifest['questions_sha256']
            or run['predictions_sha256'] != file_sha(predictions)):
        parser.error('Run is incomplete or its input/output hash has changed')
    rows = index(read_jsonl(predictions), 'predictions')
    if rows.keys() != questions.keys():
        parser.error('Prediction IDs differ from question IDs')
    items = []
    for qid, key in keys.items():
        if key['numeric'] is not None:
            expected = reference_numeric(key['numeric'])
            answer = rows[qid]['answer']
            items.append({'id': qid, 'strict': numeric_result(answer, expected),
                          'content': content_result(answer, expected)})
    record = {'diagnostic_version': 1, 'run': str(args.run_dir),
              'predictions_sha256': run['predictions_sha256'], 'questions_sha256': manifest['questions_sha256'],
              'answer_key_sha256': manifest['answer_key_sha256'],
              'policy': 'Separate diagnostic only. Accept complete JSON or final JSON code fence, including multiple lines. Never evaluate expressions, coerce types, or extract numbers from prose. Original strict score unchanged.',
              'items': items}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps(items, ensure_ascii=False))


if __name__ == '__main__':
    main()
