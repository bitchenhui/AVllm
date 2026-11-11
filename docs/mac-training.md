# Mac MLX 训练指南

主训练设备：用户已有 M2 Max / 32GB / 1TB SSD。1TB 是存储空间；模型权重、激活、优化器与系统占用统一内存。当前 M4 Pro / 24GB 已用合成样本验证两步 LoRA 的保存和重载，并完成 24 步小批领域训练。M2 Max 还未实测。

## 环境与模型

在 M2 Max 上获取仓库，并重建资料或拷贝本地 `materials/`。使用 Python 3.12 的独立环境，避免系统 Python 与训练包兼容问题：

```bash
uv venv --python 3.12 .venv-train
uv pip install --python .venv-train/bin/python 'mlx-lm[train]' huggingface_hub
.venv-train/bin/python scripts/doctor.py
uv pip freeze --python .venv-train/bin/python
```

首个成功环境的 freeze 保存进 run 目录并固化；这里没有捏造已经验证的训练包版本。先检查 `mlx_lm.lora --help`，核对快照指南 `materials/raw/training/mlx-lora.md` 与安装版本。

候选 revision 记录在 `configs/models.json`。M4 Pro 开发机已下载并校验权重，[实际推理记录](dev-baseline.md)可复查；M2 Max 训练机仍需恢复本地模型。训练前核对 revision，保存模型卡和配置，然后下载到 `models/qwen3-4b-mlx-4bit`：

```bash
.venv-train/bin/hf download mlx-community/Qwen3-4B-Instruct-2507-4bit --revision 50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b --local-dir models/qwen3-4b-mlx-4bit
```

模型结构、tokenizer、chat template 和原始文件哈希随 run 保留。模型权重由每台机器单独准备，Git 不包含权重。

## 用合成样本验证训练环境

模型下载完成后，可以用四条自造加法样本先跑通训练工具。它不读取领域候选、开发题或最终测试；只对最后一层做两步 LoRA，启用提示 masking，保存并重载适配器。运行目录需不存在。

```bash
.venv-train/bin/python scripts/smoke_mlx_fixture.py \
  --model-dir models/qwen3-4b-mlx-4bit \
  --output runs/mlx-fixture-smoke
```

M4 Pro 的[实测记录](records/2026-11-11-mlx-fixture-smoke-m4pro.json)保存了配置、输入和产物哈希。两步训练及验证 loss 均有限，14 个适配器张量可重载，7 个 LoRA B 矩阵均从零更新，重载后能生成文本。它只验证训练流程，不能用来评估领域效果、长序列内存或正式训练吞吐。

## M4 Pro 小批领域实测

四个标准的 12 道计算题（训练 8、验证 4）和 4 道源码题（训练）已完成[本机冒烟范围内的 AI 复核](../datasets/pilot-v1/m4pro-local-review.json)。逐条回看规范、固定提交和复算结果。导出副本修正两处表述：HM 通过输出参数写入索引；VVC 的 treated-as-picture 语义不含环路滤波。原候选文件未修改，其余 8 条解释候选仍待复核。该审查仅用于用户授权的本地小跑，未声称独立人工签发或公开发布许可。

[运行记录](records/2026-11-11-phase1-domain-m4pro.json)保留训练配置、分片和适配器哈希、逐阶段 loss、每道验证题的 loss 及开发集配对结果。12 条 train 和 4 条 valid 的最长模板长度分别为 219 和 208。用相同 Qwen3-4B 权重、末端 8 层、rank 8、batch 1、学习率 1e-5 跑 24 步，约两遍训练样本。训练及过程中验证共用时 16.6 秒，不含模型首次加载和重载。MLX 分配峰值约 3.13 GB（十进制），不代表整机内存占用；56 个 LoRA B 矩阵非零，适配器成功重载。

- 在相同的 4 道验证题、365 个未补齐的答案 token 上，基座 loss **3.367**，重载适配器 loss **2.280**。该比较与训练期间框架报告的批次 loss 分开记录。
- 在相同简洁提示、384 token 上限的 20 道开发题上，截断从 **6 道降到 0 道**；严格格式的计算题从 **2/4 降到 1/4**。HEVC 位深偏移题从正确变为错值，VVC 回绕仍错。16 道非数值题没有完成独立评分，不报告总体正确率。

这次验证了从复核、导出到领域 LoRA 和重载的流程。四题的验证 loss 下降不等于泛化提升；下一轮先扩展独立机制和计算反例，保留这份配置作为小批对照。

在已下载并记录模型哈希的 M4 Pro 本地目录，按以下命令复现。若审核副本和分片已经存在并通过哈希核对，可直接从训练命令开始；运行输出使用新目录。模型目录的 `avllm-model-revision.json` 为本地权重收据，字段和值见运行记录的 `model` 项，脚本会重新校验权重。

```bash
python3 scripts/materialize_phase1_local_review.py --output data/approved/phase1-m4pro-v1.jsonl
python3 scripts/prepare_training.py data/approved/phase1-m4pro-v1.jsonl --output data/splits/phase1-m4pro-v1
.venv-train/bin/python scripts/run_mlx_domain_smoke.py \
  --config configs/mlx-domain-smoke-m4pro.json --output runs/phase1-domain-m4pro-replay
```

开发集对照复用[基线命令](dev-baseline.md#运行过程)，加上 `--adapter-path runs/phase1-domain-m4pro-replay/adapter`，并换一个输出目录。分片、原始逐题输出和适配器留在本地。

## 扩充边界题后的固定步数对照

新增的四标准 12 道边界题经[逐题本地 AI 复核](../datasets/boundary-v1/m4pro-local-review.json)纳入训练副本。原 12 条训练样本保留，原 4 条验证样本逐字节相同。两轮均从同一个未微调基座开始，使用相同随机种子、配置和 24 步训练。扩充组把训练数据从 12 条增为 24 条，所以固定步数下约从两遍变为一遍；MLX 框架记录的训练 token 分别为 2036 和 1954。这是固定预算下的比较，不能分开估计数据覆盖和样本重复次数的影响。

[扩充组运行记录](records/2026-11-11-phase1-domain-m4pro-boundary.json)保存了训练、重载验证和三组开发题结果：

- 同一 4 道验证题和 365 个答案 token 上，基座 loss 为 3.367；原 12 条训练组为 2.280，扩充 24 条组为 **2.301**。扩充组训练及过程验证耗时 15.4 秒，MLX 分配峰值约 3.24 GB。
- 在同一套 20 道开发题上，严格格式的计算正确数从基座 **2/4** 到原训练组 **1/4**，扩充组回到 **2/4**。HEVC 位深偏移题恢复到基座的正确结果；AVC 初始 QP 和 VVC QP 回绕仍错误。三组截断数分别为 **6、0、1**。非数值题仍待独立复核，没有整体正确率或最终测试结果。

扩充组修复了上一轮的计算回退，尚未超过基座。优先增加分属独立机制的数值评测题并复核非数值题，再判断是否扩大训练量或调整训练预算。

```bash
python3 scripts/materialize_phase1_local_review.py --include-boundary \
  --output data/approved/phase1-m4pro-boundary-v1.jsonl
python3 scripts/prepare_training.py data/approved/phase1-m4pro-boundary-v1.jsonl \
  --output data/splits/phase1-m4pro-boundary-v1
.venv-train/bin/python scripts/run_mlx_domain_smoke.py \
  --config configs/mlx-domain-smoke-m4pro-boundary.json --output runs/phase1-domain-m4pro-boundary-replay
```

## 先检查数据，再小跑

按数据流水线生成 `data/splits/pilot`，必须有审核后训练集和独立 valid。使用同一个 tokenizer 统计完整 chat template 的长度，先保证样本不超 2048 token；不能只统计字符数，也不依赖框架静默截断。

```bash
python3 scripts/validate_samples.py data/approved/pilot.jsonl --require-approved
python3 scripts/prepare_training.py data/approved/pilot.jsonl --output data/splits/pilot
.venv-train/bin/python scripts/check_token_lengths.py data/splits/pilot/train.jsonl --tokenizer models/qwen3-4b-mlx-4bit --max-tokens 2048 --report runs/pilot-train-lengths.json
.venv-train/bin/python scripts/check_token_lengths.py data/splits/pilot/valid.jsonl --tokenizer models/qwen3-4b-mlx-4bit --max-tokens 2048 --report runs/pilot-valid-lengths.json
.venv-train/bin/mlx_lm.lora --config configs/mlx-smoke.yaml
```

冒烟配置：100 步，batch=1，8 个末端层，rank=8，长度 2048，启用 checkpointing 和 prompt masking。检查实际数据模板、loss 有限、权重保存和重载。一次成功小跑不证明专业能力提升。

## 首轮 SFT

在资源允许时使用 `configs/mlx-sft.yaml`，先检查该配置与真实数据规模匹配。它增加到 16 个末端层、rank=16、累积 4。已核对并保存的 MLX 训练循环中，iters 是微批次计数：batch1/累积4时，1600 iterations 约处理1600个样本批次、完成400个 optimizer updates。设置 iters 时按真实 train 样本数和轮数计算，并取为累积次数的整数倍；不同训练器不要直接照抄这个计数口径。

```bash
.venv-train/bin/mlx_lm.lora --config configs/mlx-sft.yaml
.venv-train/bin/mlx_lm.generate --model models/qwen3-4b-mlx-4bit --adapter-path adapters/phase1-sft --prompt '请区分标准规定的解码过程与编码器的模式搜索策略。'
```

学习率先用 valid 比较 1e-5 与 5e-5；不要承诺某个学习率最佳。训练日志记录量化方式、target modules、末端层数、rank、累积、masking、随机种子和样本 token 分布。适配器文件不包含完整的训练状态，重载适配器不等于精确恢复优化器。OOM 时先缩短样本或训练层数，batch 已为1；检查内存压力和 swap，不把依赖 swap 的完成结果当作高效配置。

## 32GB 的扩展方式

先验证4B/2048。内存有余量后按单变量尝试 4096、更多适配层或更大 rank；每次复测。8B 与更长上下文属于后续实验，需先判断4B错误是否来自容量。更多标准主要增加训练数据和总耗时，不直接让模型权重变大。

## 速度与专用机

这台闲置 M2 Max 的优势是已有、可专用运行、32GB 内存。不能仅凭芯片代际或内存带宽断言其比 M4 Pro/5060 更快。先用完全相同数据顺序、token 长度、microbatch、累积、适配层/目标模块和迭代数做100步测试，丢弃预热，记录有效训练 token/s、峰值内存和总耗时。跨 MLX/CUDA 的量化与内核不完全相同，报告是实际训练方案对比，不是纯硬件算力排名。

无需为启动第一期购买新 Mac mini。若未来瓶颈明确是训练吞吐，再按实际 workload 比较更大显存 CUDA 机器或按需 GPU；若是内存容量和常驻本地服务，再考虑更大内存 Apple 芯片设备。

参考：[MLX-LM 微调指南](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md)、[候选模型](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)。
