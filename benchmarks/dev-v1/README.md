# AVllm 开发评测 v1

四个标准各 5 道，共 20 道。每个标准有 1 道计算题和 1 道给定代码逻辑的源码题，其余覆盖原理、条件、错误前提、信息不足或跨标准比较。题面和参考答案由原标准、固定提交的源码整理；数值题的公式对照 PDF 原页。当前尚未进行独立领域同行复核。

这是用于筛选基座和检查流程的 **开发集**。答案在仓库中可见，不能用它宣称最终泛化表现。后续冻结一套机制和实验家族不同的测试题。开发题、答案及其改写不得进入训练数据或检索语料；标准原文和源码可用于正常检索。

首轮 M4 Pro 基座实验见 [运行过程和结论](../../docs/dev-baseline.md)与[运行记录](records/2026-11-11-m4pro-qwen3-4b.json)。

- `questions.jsonl`：题目、任务分类、机制分组、证据页或行号与内容哈希。
- `answer-key.jsonl`：独立参考答案、评分要点，4 道数值题另含可执行参考输入和期望值。
- `manifest.json`：两份数据的 SHA-256、题量与审核状态。修改题目或评分口径时升版本，不用新文件回填旧成绩。

其中代码题使用经过核对的等价描述，保留提交和行号，可以在恢复资料后阅读真实实现。计算题提供公式或映射规则，主要检查计算正确性；它们不能单独衡量模型对标准的记忆。

## 无需模型即可执行

在仓库根目录：

```bash
python3 scripts/dev_benchmark.py verify
python3 scripts/dev_benchmark.py verify --sources
python3 -m unittest discover -s tests -v
```

第一条只校验开发集并复算 4 道数值题。第二条需要本地已有 PDF、提取文本与源码，额外检查 27 个去重后的证据定位。文件匹配不等于模型正确或专业答案经过人类复核。

## 模型准备好后

用已安装 MLX-LM 的训练环境运行，模型目录需事先按 [Mac 微调指南](../../docs/mac-training.md) 下载。本脚本仅打开本地模型，不联网找模型或读取答案文件作为推理输入。先跑 A（基座＋题目给定条件）：

```bash
.venv-train/bin/python scripts/dev_benchmark.py run \
  --model-dir models/qwen3-4b-mlx-4bit \
  --model-id mlx-community/Qwen3-4B-Instruct-2507-4bit \
  --revision 50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b \
  --output runs/dev-v1-qwen3-base

python3 scripts/dev_benchmark.py score --run-dir runs/dev-v1-qwen3-base
```

模型名和 revision 是运行人声明的来源；实际权重和 tokenizer 文件另有 SHA-256。默认贪心解码、384 个生成 token，MLX 依赖版本、生成参数和题目哈希写入运行目录。每个模型只加载一次，并记录逐题耗时、输入/输出 token 和结束原因。重新运行请用新的输出目录；中断的运行标记为 incomplete，不能当作完整结果计分。报告单列触及生成上限的题。

如果要检查答案是否因复述题面而被截断，可使用 `--system-prompt-file prompts/dev-concise-system.txt` 做单独的提示词对照。沿用同一模型、题目和 token 预算，另设输出目录。把两种提示词当作不同条件；测微调收益时，同一对照组必须用同一提示词。

数值题最后一行要求是指定键的整数 JSON；允许外层 Markdown 代码围栏。合法 JSON 的数值错误记为 `incorrect`，格式不符（包括重复键、布尔值、缺键）记为 `unparseable`，两者分别报告。不能把自动评分扩展解释为 20 道题的总正确率。

`score` 会生成 `manual-review.jsonl`，列出另外 16 道题的模型回答、参考答案和评分要点。把 `ratings` 中的 `null` 改为 `0` 或 `1`，再跑同一评分命令更新 `scores.json`。已填写的评审文件不会被覆盖；分数区分已评分点和全部评分点。

后续 C（同基座＋适配器）传入 `--adapter-path`；B 与 D 增加同一个 `--contexts` 文件，每行仅含 `id` 和从标准/源码取得的 `context`，每题一行。脚本不执行检索；冻结的检索结果由外部准备并保存 SHA-256。对比时匹配生成预算、精度、题目与上下文，不把条件不同的结果归因于微调。

## 数据隔离

`configs/holdout-groups.json` 登记此开发集。生成证据包时，命中机制组或相同证据会标记 `assigned_split=dev`。训练导出会拒绝匹配开发题 ID、机制组、规范化题面或完全相同锁定证据的样本，并记录开发题文件哈希。这些规则只能拦住显式重合；相邻页、重叠源码片段和改写题仍需审核。
