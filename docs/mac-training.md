# Mac MLX 训练指南

主训练设备：用户已有 M2 Max / 32GB / 1TB SSD。1TB 是存储空间；模型权重、激活、优化器与系统占用统一内存。当前 M4 Pro / 24GB 可先用于资料和流程开发。没有在 M2 Max 上实际跑过训练，以下为起始配置。

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
