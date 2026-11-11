#!/usr/bin/env python3
"""Exercise MLX LoRA save/reload using only four synthetic arithmetic examples."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

from dev_benchmark import file_sha, write_json

FIXTURES = {'train': ((4, 3), (8, 2)), 'valid': ((6, 5), (9, 4))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    model = args.model_dir.resolve()
    if not (model / 'config.json').is_file() or not any(model.glob('*.safetensors')):
        parser.error('Supply an existing local MLX checkpoint')
    output = args.output.resolve()
    data, adapter = output / 'data', output / 'adapter'
    output.mkdir(parents=True, exist_ok=False)
    data.mkdir()
    for split, pairs in FIXTURES.items():
        rows = [{'messages': [{'role': 'user', 'content': f'{a} 加 {b} 等于多少？'},
                              {'role': 'assistant', 'content': f'{a + b}。'}]} for a, b in pairs]
        (data / f'{split}.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
    # JSON is valid YAML and avoids reliance on implicit float parsing.
    config = {'model': str(model), 'train': True, 'fine_tune_type': 'lora', 'data': str(data),
              'seed': 42, 'num_layers': 1, 'batch_size': 1, 'iters': 2, 'learning_rate': 0.00001,
              'max_seq_length': 128, 'grad_checkpoint': True, 'grad_accumulation_steps': 1,
              'mask_prompt': True, 'val_batches': 2, 'steps_per_report': 1, 'steps_per_eval': 2,
              'save_every': 2, 'adapter_path': str(adapter),
              'lora_parameters': {'rank': 8, 'dropout': 0.0, 'scale': 16.0}}
    write_json(output / 'config.json', config)
    env = {**os.environ, 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1'}
    started = time.perf_counter()
    with (output / 'train.log').open('x', encoding='utf-8') as log:
        result = subprocess.run([sys.executable, '-m', 'mlx_lm', 'lora', '--config', str(output / 'config.json')],
                                env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
    elapsed = round(time.perf_counter() - started, 3)
    if result.returncode:
        parser.exit(result.returncode, f'Training subprocess failed; see {output / "train.log"}\n')
    weights = adapter / 'adapters.safetensors'
    if not weights.is_file() or not weights.stat().st_size:
        parser.error(f'Missing adapter weights: {weights}')
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    import mlx.core as mx
    from mlx_lm import generate, load
    tensors = mx.load(str(weights))
    if not tensors or not all(mx.all(mx.isfinite(value)).item() for value in tensors.values()):
        parser.error('Adapter tensors missing or non-finite')
    b_matrices = [value for name, value in tensors.items() if name.endswith('.lora_b')]
    nonzero_b_matrices = sum(bool(mx.any(value != 0).item()) for value in b_matrices)
    if not nonzero_b_matrices:
        parser.error('No LoRA B matrix updated from zero')
    tuned, tokenizer = load(str(model), adapter_path=str(adapter))
    prompt = tokenizer.apply_chat_template([{'role': 'user', 'content': '2 加 3 等于多少？'}],
                                           tokenize=False, add_generation_prompt=True)
    answer = generate(tuned, tokenizer, prompt=prompt, max_tokens=8, verbose=False)
    if not answer.strip():
        parser.error('Reloaded adapter produced no text on the fixture prompt')
    record = {'purpose': 'synthetic_fixture_only; no domain data or benchmark items', 'status': 'train_save_reload_passed',
              'platform': platform.platform(), 'machine': subprocess.check_output(['sysctl', '-n', 'machdep.cpu.brand_string'], text=True).strip(),
              'mlx_lm_version': importlib.metadata.version('mlx-lm'), 'train_seconds_includes_load': elapsed,
              'train_examples': len(FIXTURES['train']), 'valid_examples': len(FIXTURES['valid']),
              'iterations': config['iters'], 'layers': config['num_layers'], 'max_seq_length': config['max_seq_length'],
              'mask_prompt': config['mask_prompt'], 'base_weights_sha256': {p.name: file_sha(p) for p in sorted(model.glob('*.safetensors'))},
              'artifact_sha256': {str(p.relative_to(output)): file_sha(p) for p in (
                  output / 'config.json', output / 'train.log', data / 'train.jsonl', data / 'valid.jsonl',
                  weights, adapter / 'adapter_config.json')},
              'adapter_tensors': len(tensors), 'lora_b_matrices': len(b_matrices),
              'nonzero_lora_b_matrices': nonzero_b_matrices, 'reload_generated_nonempty_text': True}
    write_json(output / 'manifest.json', record)
    print(f'Two fixture steps completed in {elapsed}s; saved and reloaded {len(tensors)} adapter tensors.')


if __name__ == '__main__':
    main()
