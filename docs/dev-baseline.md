# Qwen3-4B 开发基线：先分清提示、格式和算法错误

2026-11-11，Apple M4 Pro / 24 GB，macOS 26.0，Python 3.12.14、MLX 0.32.4、MLX-LM 0.32.2。使用本地 `mlx-community/Qwen3-4B-Instruct-2507-4bit`，revision `50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b`；2,263,022,417 字节的权重已按发布元数据校验 SHA-256。

[机器可读运行记录](../benchmarks/dev-v1/records/2026-11-11-m4pro-qwen3-4b.json)保存模型文件、题面、评分键、逐题输出和初次评分的哈希，另有[实测依赖快照](../benchmarks/dev-v1/records/2026-11-11-m4pro-qwen3-4b-requirements.txt)。运行目录中的逐题输出和待复核表留在本地。

## 运行过程

1. 在开发机创建独立 Python 环境并确认 MLX 识别到 Apple GPU。该环境已验证本地推理；LoRA 训练依赖和 M2 Max 训练仍待实测。
2. 下载固定 revision 的模型配置、分词器和权重。权重大文件传输有多段超时，重复请求整段会丢掉该段已有进度；本次改成从已保存的字节位置续传。只有拼接后的完整权重通过 SHA-256 校验，才交给推理脚本。新机器优先按 [Mac 指南](mac-training.md#环境与模型)准备模型。
3. 本地运行默认提示，检查原始输出后发起第二轮；第二轮仅替换系统提示，保留原始运行和初次评分。

复跑时先准备模型目录。下面使用新运行目录，避免覆盖原记录：

```bash
uv venv --python 3.12 .venv-baseline
uv pip install --python .venv-baseline/bin/python \
  -r benchmarks/dev-v1/records/2026-11-11-m4pro-qwen3-4b-requirements.txt

run_baseline() {
  HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv-baseline/bin/python scripts/dev_benchmark.py run \
    --model-dir models/qwen3-4b-mlx-4bit \
    --model-id mlx-community/Qwen3-4B-Instruct-2507-4bit \
    --revision 50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b \
    --max-tokens 384 --seed 42 --output "$@" &&
  .venv-baseline/bin/python scripts/dev_benchmark.py score --run-dir "$1"
}

run_baseline runs/dev-v1-qwen3-replay-default
run_baseline runs/dev-v1-qwen3-replay-concise --system-prompt-file prompts/dev-concise-system.txt
```

## 实测结果

两轮都使用 [20 道开发题](../benchmarks/dev-v1/README.md)，无适配器、无额外检索，贪心解码，每题最多 384 个生成 token。两份运行清单只有系统提示和输出文件哈希不同。原始运行在 `runs/dev-v1-qwen3-base-m4pro/` 和 `runs/dev-v1-qwen3-base-m4pro-concise/`。每个目录包含 `manifest.json`、`predictions.jsonl`、`scores.json` 和 `manual-review.jsonl`。计时仅为本机推理；未测峰值内存和训练吞吐。

- **默认提示**：20 题全部产出；16 题达到生成上限。4 道计算题严格格式评分为 0 对、0 个可解析的错值、4 个无法按单行整数 JSON 解析。累计逐题耗时 100.9 秒，不含模型加载。
- **简洁提示**：20 题全部产出；6 题达到生成上限。4 道计算题为 2 对、1 个错值、1 个格式未通过。累计逐题耗时 91.2 秒，不含模型加载。
- **16 道非数值题**：原始答案和 48 个评分点已准备好，尚无独立评分，不能计算 20 道题的整体正确率。

## 从原始回答看到的错误

- **格式与结果分开看。** 默认提示下，HEVC 和 AV1 的两道计算题数值正确，但输出了多行 JSON；AVC 写的是等于正确值的算式，而非整数。简洁提示下 AVC 改成了可解析的整数，却给了错误值。不能把格式通过当作算法正确。
- **有错误跨提示保留。** VVC 的 QP 回绕题两轮均输出相同错值，严格评分还会把它归为多行格式未通过。简洁提示下，HEVC 的变换跳过题也错误地否定了题设下的系数缩放；给定的 VTM 源码题则额外声称调用 LFNST 受 skip 分支约束，和题面给出的调用顺序不符。
- **先固定提示再比较微调。** 简洁提示让本轮少截断 10 题，仍有 6 题未完整结束。首轮微调前可用该提示建立新的 A 对照，微调后 C 使用同一提示和预算。检索对照 B/D 同样固定提示和上下文。

下一批训练候选优先覆盖三类能力：有符号整数与回绕、标准语法的使能与实际应用条件、给定源码片段中的调用与生效条件。选择与开发、验证和最终测试不重合的机制及证据；不得把这次错题、答案或改写放进训练或检索库。

## 本阶段的数据核验

运行以下命令确认数据分隔和来源锁。最终测试核验命令需要评测机上的隔离副本，Git clone 不包含题面和答案。

```bash
python3 scripts/dev_benchmark.py verify --sources
python3 scripts/verify_pilot_batch.py
python3 scripts/verify_validation_batch.py
python3 scripts/verify_holdout_draft.py
python3 -m unittest discover -s tests -v
```

- 开发集 20 题、27 处来源定位和 4 个数值参考通过核验；本次模型只运行这个题集。
- 训练候选 16 条和独立验证候选 8 条已核验来源、显式重合和可复算项，均待入训复核。
- 最终测试草案 8 道，4 个数值参考、9 处来源定位通过核验。只保存版本哈希和机制登记，未用于本轮推理或提示调整。
- 仓库 16 项测试通过。首轮 LoRA、最终测试评分和微调收益目前都没有实测结果。

后续每个有意义的实验保留运行编号、唯一改动、环境、输入版本、原始产物哈希和结论。补充人工评分时另记评分状态和版本，保留初次自动评分记录。
