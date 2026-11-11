#!/usr/bin/env python3
"""Build a source-assisted dev control from question evidence, without answer keys."""
import argparse
import json
from pathlib import Path

from avllm_data import ROOT, evidence_text, sha
from dev_benchmark import load_questions, verify_sources, write_json


def select_excerpt(text, selection):
    if (not isinstance(selection, dict) or set(selection) != {'parent_sha256', 'start', 'end'}
            or sha(text.encode()) != selection['parent_sha256']):
        raise ValueError('Selection does not match the verified parent evidence')
    start, end = selection['start'], selection['end']
    lines = text.splitlines()
    if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
        raise ValueError('Invalid inclusive excerpt line range')
    return '\n'.join(lines[start - 1:end])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--selection', type=Path, help='Hash-pinned excerpt ranges per question and evidence item')
    args = parser.parse_args()
    manifest, questions = load_questions()
    checked = verify_sources(questions)
    selections = None
    if args.selection:
        selection = json.loads(args.selection.read_text())
        if (not isinstance(selection, dict) or selection.get('questions_sha256') != manifest['questions_sha256']
                or not isinstance(selection.get('items'), dict) or set(selection['items']) != set(questions)):
            raise ValueError('Selection must cover exactly the locked questions')
        selections = selection['items']
    sources = {s['id']: s for s in json.loads((ROOT / 'materials/sources.lock.json').read_text())['sources']}
    rows, provenance = [], []
    for qid, question in questions.items():
        parts, excerpts = [], []
        spans = selections[qid] if selections is not None else None
        if selections is not None and (not isinstance(spans, list) or len(spans) != len(question['evidence'])):
            raise ValueError(f'{qid}: selection must retain every evidence item')
        for i, ev in enumerate(question['evidence']):
            source = sources[ev['source_id']]
            text = evidence_text(source, ev['locator'])
            if sha(text.encode()) != ev['snippet_sha256']:
                raise ValueError(f'{qid}: evidence changed')
            if spans is not None:
                span = spans[i]
                text = select_excerpt(text, span)
                excerpts.append({**span, 'excerpt_sha256': sha(text.encode())})
            parts.append(f"Source: {source['title']}\nRevision: {ev['source_revision']}\n"
                         f"Locator: {json.dumps(ev['locator'], ensure_ascii=False)}\n{text}")
        rows.append({'id': qid, 'context': '\n\n'.join(parts)})
        provenance.append({'id': qid, 'evidence': question['evidence'], **({'excerpts': excerpts} if spans is not None else {})})
    args.output.mkdir(parents=True, exist_ok=False)
    contents = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows)
    (args.output / 'contexts.jsonl').write_text(contents, encoding='utf-8')
    write_json(args.output / 'manifest.json', {
        'method': 'oracle_evidence_locators_from_dev_questions',
        'note': 'Source-assisted reading control; not end-to-end retrieval quality. No answer key loaded.',
        'questions_sha256': manifest['questions_sha256'], 'contexts_sha256': sha(contents.encode()),
        'source_lock_sha256': sha((ROOT / 'materials/sources.lock.json').read_bytes()),
        **({'selection_sha256': sha(args.selection.read_bytes())} if args.selection else {}),
        'source_locators_verified': checked, 'items': provenance,
    })
    print(f'Built {len(rows)} source-assisted contexts from {checked} verified evidence locators')


if __name__ == '__main__':
    main()
