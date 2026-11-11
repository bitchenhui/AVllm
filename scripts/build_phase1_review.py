#!/usr/bin/env python3
"""Prepare a local review queue for the phase-one candidates without approving them."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
from textwrap import indent
from urllib.parse import quote

from avllm_data import ROOT, evidence_text, read_jsonl, read_split_registry, registered_split, sha
from dev_benchmark import file_sha, write_json
from verify_pilot_batch import verify as verify_training
from verify_validation_batch import verify as verify_validation


def link(path, output):
    return quote(os.path.relpath(path, output), safe='/')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if ROOT / 'work' not in output.parents or output.exists():
        parser.error('Use a new output directory under work/ for local source excerpts')
    lock = ROOT / 'materials/sources.lock.json'
    sources = {s['id']: s for s in json.loads(lock.read_text())['sources']}
    registry = read_split_registry()
    queue, evidence, batch_hashes = [], {}, {}
    for batch, verify in [('pilot-v1', verify_training), ('validation-v1', verify_validation)]:
        directory = ROOT / 'datasets' / batch
        report_path = directory / 'verification-report.json'
        report = verify()
        if report != json.loads(report_path.read_text()):
            raise ValueError(f'{batch}: checked report differs from the recorded snapshot')
        dataset = directory / 'candidates.jsonl'
        fixture = directory / 'numeric-cases.json'
        cases = json.loads(fixture.read_text())['cases']
        batch_hashes[batch] = {'candidates_sha256': file_sha(dataset), 'verification_report_sha256': file_sha(report_path),
                               'numeric_cases_sha256': file_sha(fixture)}
        for row in read_jsonl(dataset):
            entries = []
            for ev in row['evidence']:
                source, loc = sources[ev['source_id']], ev['locator']
                digest = ev['snippet_sha256']
                if digest not in evidence:
                    excerpt = evidence_text(source, loc)
                    if sha(excerpt.encode()) != digest:
                        raise ValueError(f'{row["id"]}: source excerpt changed')
                    evidence[digest] = excerpt
                original = ROOT / source['path']
                if loc['type'] == 'file_lines':
                    original /= loc['path']
                target = link(original, output) + (f'#page={loc["page"]}' if loc['type'] == 'pdf_page' else '')
                entries.append({**ev, 'title': source['title'], 'original_local_link': target,
                                'excerpt_path': f'evidence/{digest}.txt', 'rights_record': source['rights'],
                                'source_eligibility': source['training_eligibility'],
                                'license_links': [link(ROOT / p, output) for p in source.get('license_files', [])]})
            qid = row['id']
            numeric = {'fixture': cases[qid], 'independent_result': report['numeric_answers'][qid]} if qid in cases else None
            queue.append({'id': qid, 'batch': batch, 'split': registered_split(row['split_group'], registry),
                          'candidate_sha256': sha(json.dumps(row, ensure_ascii=False, sort_keys=True).encode()),
                          'topic': row['topic'], 'codecs': row['codecs'], 'task_type': row['task_type'],
                          'messages': row['messages'], 'sources': entries, 'numeric_check': numeric,
                          'prior_checks': [{**c, 'local_link': link(ROOT / c['artifact'], output)} for c in row['verification']['checks']],
                          'review_status': 'pending', 'eligibility_status': 'pending'})

    (output / 'evidence').mkdir(parents=True, exist_ok=False)
    for digest, content in evidence.items():
        (output / 'evidence' / f'{digest}.txt').write_text(content, encoding='utf-8')
    queue_path = output / 'queue.jsonl'
    queue_path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in queue), encoding='utf-8')
    summary = ['# 第一期候选复核材料', '', '这里的记录全部待复核。请分别写下技术判断和使用条件判断；原文以锁定 PDF 或源码为准。',
               '抽取文本仅供定位，公式、上下标、表格和代码上下文请回看原件。程序复算与已有核验不能代替独立签发。', '']
    for row in queue:
        summary.extend([f'## {row["id"]} · {row["split"]} · {row["task_type"]}', '',
                        f'候选 SHA-256：`{row["candidate_sha256"]}`', ''])
        for msg in row['messages']:
            summary.extend([f'**{msg["role"]}**', '', indent(msg['content'], '    '), ''])
        for i, item in enumerate(row['sources'], 1):
            loc = json.dumps(item['locator'], ensure_ascii=False)
            summary.append(f'- 来源 {i}：{item["title"]}，`{loc}`。'
                           f' [原件]({item["original_local_link"]}) · [抽取片段]({item["excerpt_path"]})。'
                           f' 使用条件记录：{item["rights_record"]}')
            for j, license_link in enumerate(item['license_links'], 1):
                summary.append(f'  - [许可或通知文件 {j}]({license_link})')
        if row['numeric_check'] is not None:
            summary.append(f'- 独立复算：`{json.dumps(row["numeric_check"]["independent_result"], ensure_ascii=False)}`；输入见 `queue.jsonl`。')
        summary.append('- 已有核验：' + '、'.join(f'[{c["kind"]}]({c["local_link"]})' for c in row['prior_checks']))
        summary.extend(['', '待填写：技术结论、适用条件或修订点、使用条件结论、审核人和日期。', ''])
    (output / 'review.md').write_text('\n'.join(summary), encoding='utf-8')
    manifest = {'version': 1, 'status': 'review_pending', 'candidates': len(queue),
                'by_split': dict(Counter(row['split'] for row in queue)), 'evidence_excerpts': len(evidence),
                'numeric_checks': sum(row['numeric_check'] is not None for row in queue),
                'approved': 0, 'source_lock_sha256': file_sha(lock),
                'split_registry_sha256': file_sha(ROOT / 'configs/holdout-groups.json'),
                'batches': batch_hashes, 'queue_sha256': file_sha(queue_path), 'review_sha256': file_sha(output / 'review.md')}
    write_json(output / 'manifest.json', manifest)
    print(f'Prepared {len(queue)} pending reviews with {len(evidence)} unique source excerpts in {output}')


if __name__ == '__main__':
    main()
