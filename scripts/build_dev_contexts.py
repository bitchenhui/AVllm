#!/usr/bin/env python3
"""Build a source-assisted dev control from question evidence, without answer keys."""
import argparse
import json
from pathlib import Path

from avllm_data import ROOT, evidence_text, sha
from dev_benchmark import load_questions, verify_sources, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest, questions = load_questions()
    checked = verify_sources(questions)
    sources = {s['id']: s for s in json.loads((ROOT / 'materials/sources.lock.json').read_text())['sources']}
    rows, provenance = [], []
    for qid, question in questions.items():
        parts = []
        for ev in question['evidence']:
            source = sources[ev['source_id']]
            text = evidence_text(source, ev['locator'])
            if sha(text.encode()) != ev['snippet_sha256']:
                raise ValueError(f'{qid}: evidence changed')
            parts.append(f"Source: {source['title']}\nRevision: {ev['source_revision']}\n"
                         f"Locator: {json.dumps(ev['locator'], ensure_ascii=False)}\n{text}")
        rows.append({'id': qid, 'context': '\n\n'.join(parts)})
        provenance.append({'id': qid, 'evidence': question['evidence']})
    args.output.mkdir(parents=True, exist_ok=False)
    contents = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows)
    (args.output / 'contexts.jsonl').write_text(contents, encoding='utf-8')
    write_json(args.output / 'manifest.json', {
        'method': 'oracle_evidence_locators_from_dev_questions',
        'note': 'Source-assisted reading control; not end-to-end retrieval quality. No answer key loaded.',
        'questions_sha256': manifest['questions_sha256'], 'contexts_sha256': sha(contents.encode()),
        'source_lock_sha256': sha((ROOT / 'materials/sources.lock.json').read_bytes()),
        'source_locators_verified': checked, 'items': provenance,
    })
    print(f'Built {len(rows)} source-assisted contexts from {checked} verified evidence locators')


if __name__ == '__main__':
    main()
