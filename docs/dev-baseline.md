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

## 后续初审与来源辅助对照

对简洁提示运行的 16 道非数值题，已逐评分点完成 [AI 初审记录](../benchmarks/dev-v1/records/2026-11-11-concise-ai-review.json)。每点保存建议分数及理由，另标记缺失条件、虚构字段、计算、代码分支、矛盾和截断等问题。此初审与题目作者并不独立，属于待人工复核的诊断；原始 manual-review 和 scores 未被改写。复合评分点缺失必要部分时不计整点，因此部分正确回答也可能在该点得 0。

随后完成 [来源辅助对照记录](../benchmarks/dev-v1/records/2026-11-11-source-assisted.json)。使用同一模型、简洁系统提示、20 道题、贪心解码和 384 token 输出预算，仅追加资料上下文。资料来自问题中已锁定的 27 处标准页/源码定位，未读取评分键。这是预先知道相关来源的阅读能力对照，不能代表自动检索器的查找能力。

该轮 20 题全部完成，9 题以 length 结束，累计逐题耗时 144.6 秒；最长输入 3979 token。严格格式的 4 道计算题为 0 对、2 个错值、2 个格式不符。逐条查看时，HEVC 的数值正确但采用多行 JSON，VVC 同时存在多行格式和错误数值；H.264 和 AV1 都给了可解析的错误整数。不能把格式未通过简单解释成不会计算。

观察到的局部变化：

- HEVC 变换跳过题从否定缩放改为肯定缩放；x265 代码题的整数商从错误的 5 改为 6。
- VVC 的依赖量化题给出了正确字段 sh_dep_quant_used_flag；源码题也不再给调用点附加非 skip 限制。
- AV1 lossless 题从编造开关改为列出 qindex 和五个分量 delta 条件，后续解释仍有不准确之处。
- VVC 划分题仍把四叉树描述成二分；算术错误、无根据的补充和长篇复述仍存在。与无资料简洁提示相比，截断数从 6 增到 9；AV1 计算题也从正确变为错值。

这些观察说明某些错误能通过提供证据纠正，尚不能得出整体质量改善的结论。后续先把资料从整页缩到完整相关条款，保留条件、公式和可追溯定位，再做同预算对照；同时为有符号整数和分支理解准备不同机制的训练候选。切勿把本次评分或错题改写纳入训练。

复跑命令（输出目录需不存在）：

```bash
python3 scripts/build_dev_contexts.py --output runs/dev-v1-source-contexts-replay
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv-train/bin/python scripts/dev_benchmark.py run \
  --model-dir models/qwen3-4b-mlx-4bit \
  --model-id mlx-community/Qwen3-4B-Instruct-2507-4bit \
  --revision 50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b \
  --system-prompt-file prompts/dev-concise-system.txt --max-tokens 384 --seed 42 \
  --contexts runs/dev-v1-source-contexts-replay/contexts.jsonl \
  --output runs/dev-v1-qwen3-source-assisted-replay
python3 scripts/dev_benchmark.py score --run-dir runs/dev-v1-qwen3-source-assisted-replay
```

## 精简来源与输出预算对照

[六组对照记录](../benchmarks/dev-v1/records/2026-11-11-context-budget-comparison.json)覆盖无资料、整页资料和精简片段，各跑 384 与 768 token 两种输出上限。六组共用权重、20 道题、简洁提示、采样设置和机器。精简版按[固定行段](../benchmarks/dev-v1/compact-context-v1.json)从题目的 27 处来源定位中截取，保留父文本和摘录哈希，源码定位完整保留。行段由开发题选择，仍是已知来源对照；删减改变了上下文内容和长度，不能单独归因于长度。

- 同为 384 token，精简片段将 20 题的总输入从 33,550 降到 15,899 token（约少 53%），截断从 9 道降至 7 道；无资料组截断 6 道。逐题推理耗时之和为整页 144.6 秒、精简 91.2 秒，这是一轮本地运行，未重复测时。
- 上限提高到 768 后，无资料、整页、精简分别截断 1、5、2 道。三组中，原先正常结束的回答都逐字不变；原先截断的回答都仍是对应长回答的前缀。四道计算题均在 384 预算内结束，因此提高上限没有改变它们。
- 严格格式下，无资料、整页、精简分别答对 2、0、1 道计算题。将多行 JSON 的内容单独诊断后，分别是 2、1、2 道数值正确。精简组纠正了 AVC 的数值，但 AV1 从正确变为错误；VVC 的 QP 回绕在三种上下文下都算错。
- 精简版没有保住整页版的所有局部收益。例如 HEVC 变换跳过题的精简版同时陈述相反的缩放判断，768 预算下最终仍答错。不能据此选定某种资料策略有更高整体准确率；16 道非数值题没有完成跨条件的独立复核。

计算诊断只接受完整 JSON 对象或终末 JSON 代码围栏，允许换行。它不求值表达式、不从解释文字猜数值，且不修改原始严格分数。后续精简材料时，需把必要条件和例外一起保留，重点复核变换分支、字段语义和整数运算；开发题结果只用于诊断。

复跑精简对照（使用未创建的运行目录）：

```bash
python3 scripts/build_dev_contexts.py --selection benchmarks/dev-v1/compact-context-v1.json \
  --output runs/dev-v1-compact-contexts-replay
for budget in 384 768; do
  HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv-train/bin/python scripts/dev_benchmark.py run \
    --model-dir models/qwen3-4b-mlx-4bit \
    --model-id mlx-community/Qwen3-4B-Instruct-2507-4bit \
    --revision 50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b \
    --system-prompt-file prompts/dev-concise-system.txt --max-tokens "$budget" --seed 42 \
    --contexts runs/dev-v1-compact-contexts-replay/contexts.jsonl \
    --output "runs/dev-v1-qwen3-compact-replay-$budget" || break
done
python3 scripts/summarize_dev_runs.py \
  --runs runs/dev-v1-qwen3-compact-replay-384 runs/dev-v1-qwen3-compact-replay-768 \
  --context-manifest runs/dev-v1-compact-contexts-replay/manifest.json \
  --output runs/dev-v1-compact-replay-summary.json
```
