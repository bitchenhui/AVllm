#!/usr/bin/env python3
"""Archive comparable development runs and separate numeric content from formatting."""
import argparse
from collections import Counter
import json
from itertools import combinations
from pathlib import Path

from avllm_data import read_jsonl
from dev_benchmark import file_sha, index, load_key, load_questions, numeric_result, reference_numeric
from diagnose_numeric import content_result

FIXED = ('declared_model_id', 'declared_revision', 'model_file_sha256', 'adapter_file_sha256',
         'system_prompt', 'temperature', 'seed', 'mlx_lm_version', 'platform', 'questions_sha256')


def summarize(paths, context_manifests=()):
    benchmark, questions = load_questions()
    keys = load_key(benchmark, questions)
    runs, outputs, common = [], [], None
    for path in paths:
        manifest = json.loads((path / 'manifest.json').read_text())
        predictions = path / 'predictions.jsonl'
        if (manifest['status'] != 'completed' or manifest['questions_sha256'] != benchmark['questions_sha256']
                or manifest['predictions_sha256'] != file_sha(predictions)):
            raise ValueError(f'{path}: incomplete run or changed data')
        fixed = {k: manifest[k] for k in FIXED}
        if common is None:
            common = fixed
        elif common != fixed:
            raise ValueError(f'{path}: fixed controls differ; use separate comparisons')
        rows = index(read_jsonl(predictions), 'predictions')
        if rows.keys() != questions.keys():
            raise ValueError(f'{path}: prediction IDs differ')
        outputs.append(rows)
        numeric = []
        for qid, key in keys.items():
            if key['numeric'] is not None:
                expected = reference_numeric(key['numeric'])
                numeric.append({'id': qid, 'strict': numeric_result(rows[qid]['answer'], expected),
                                'content': content_result(rows[qid]['answer'], expected)})
        def counts(field):
            raw = Counter(r[field] for r in numeric)
            return {key: raw[key] for key in ('correct', 'incorrect', 'unparseable')}
        runs.append({
            'run': str(path), 'run_manifest_sha256': file_sha(path / 'manifest.json'),
            'predictions_sha256': manifest['predictions_sha256'], 'condition': manifest['condition'],
            'contexts_sha256': manifest['contexts_sha256'], 'max_tokens': manifest['max_tokens'],
            'questions': len(rows), 'numeric_strict': counts('strict'), 'numeric_content': counts('content'),
            'numeric_items': numeric,
            'length_stop_ids': [qid for qid, r in rows.items() if r['finish_reason'] == 'length'],
            'input_tokens_total': sum(r['prompt_tokens'] for r in rows.values()),
            'input_tokens_max': max(r['prompt_tokens'] for r in rows.values()),
            'generation_tokens_total': sum(r['generation_tokens'] for r in rows.values()),
            'seconds_sum_excludes_model_load': round(sum(r['seconds'] for r in rows.values()), 4),
        })
    context_provenance = []
    used_contexts = {r['contexts_sha256'] for r in runs if r['contexts_sha256']}
    for path in context_manifests:
        manifest = json.loads(path.read_text())
        if manifest['contexts_sha256'] not in used_contexts or manifest['questions_sha256'] != benchmark['questions_sha256']:
            raise ValueError(f'{path}: context manifest does not match a run')
        context_provenance.append({'manifest_sha256': file_sha(path), 'contexts_sha256': manifest['contexts_sha256'],
                                   'source_lock_sha256': manifest['source_lock_sha256'],
                                   'source_locators_verified': manifest['source_locators_verified'],
                                   'selection_sha256': manifest.get('selection_sha256')})
    budget_pairs = []
    for (a, a_rows), (b, b_rows) in combinations(zip(runs, outputs), 2):
        if a['contexts_sha256'] != b['contexts_sha256'] or a['max_tokens'] == b['max_tokens']:
            continue
        if a['max_tokens'] > b['max_tokens']:
            a, b, a_rows, b_rows = b, a, b_rows, a_rows
        completed = [qid for qid, row in a_rows.items() if row['finish_reason'] != 'length']
        budget_pairs.append({'short_run': a['run'], 'long_run': b['run'],
                             'short_answers_are_prefix_count': sum(b_rows[qid]['answer'].startswith(row['answer'])
                                                                  for qid, row in a_rows.items()),
                             'short_completed_count': len(completed),
                             'short_completed_unchanged_count': sum(a_rows[qid]['answer'] == b_rows[qid]['answer']
                                                                    for qid in completed)})
    return {'record_version': 1, 'purpose': 'development_context_and_output_budget_comparison',
            'fixed_controls': common, 'answer_key_sha256': benchmark['answer_key_sha256'],
            'numeric_diagnostic_script_sha256': file_sha(Path(__file__).with_name('diagnose_numeric.py')),
            'non_numeric_review_status': 'not_aggregated; independent_review_pending',
            'limits': 'Known source locators, not automatic retrieval. Four arithmetic items; no overall accuracy or fine-tuning benefit claim.',
            'context_provenance': context_provenance, 'budget_pairs': budget_pairs, 'runs': runs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--context-manifest', type=Path, action='append', default=[])
    args = parser.parse_args()
    if len(args.runs) != len(set(args.runs)):
        parser.error('Duplicate run directory')
    report = summarize(args.runs, args.context_manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write('\n')
    for r in report['runs']:
        print(r['run'], 'limit', r['max_tokens'], 'length stops', len(r['length_stop_ids']),
              'strict', r['numeric_strict'], 'content', r['numeric_content'])


if __name__ == '__main__':
    main()
