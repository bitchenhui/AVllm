# AVllm

面向 H.264/AVC、H.265/HEVC、H.266/VVC 和 AV1 的本地编解码算法专业语言模型项目。第一期同时覆盖四个标准，按算法模块逐步做深。目标任务是原理解释、可核算推导、指定版本源码分析和可复现实验分析。

## 从这里开始

1. 查看 [资料盘点](materials/INVENTORY.md)：实际下载结果、SHA-256、Git 提交和获取地址。
2. 阅读 [第一期落地方案](docs/phase1-plan.md)：各阶段输入、产物、验收和下一步；直接开始见 [下一步操作](docs/next-steps.md)。
3. 使用 [20 道开发题和基线工具](benchmarks/dev-v1/README.md) 检查模型表现；查看从不同机制整理的 [16 条训练候选](datasets/pilot-v1/README.md) 和 [数据流水线](docs/data-pipeline.md)。
4. 在闲置的 **M2 Max / 32GB / 1TB SSD** 上按 [Mac 微调指南](docs/mac-training.md) 做 4B 量化 LoRA 实验。
5. 用 [评测协议](docs/evaluation.md) 比较未微调与微调模型，检索与工具条件保持一致。

## 本次资料库范围

- 官方标准：H.264 (06/2026)、H.265 (01/2026)、H.266 (01/2026)、AV1 v1.0.0-errata1 的发布 PDF。
- 参考软件及实现：JM 19.0、HM、VTM、x264、x265、VVenC、VVdeC、libaom、SVT-AV1、dav1d。
- 工程与研究资料：x265 算法选项、FFmpeg/ffprobe、AV1/VVC 综述、质量度量入口。
- 训练资料：QLoRA、Self-Instruct、合成数据与模仿训练研究、MLX-LM 指南、候选模型卡。
- 测试序列：UVG、Xiph 的来源索引；视频文件另行按实验需要选择，不在此阶段批量下载。

这是第一期核心资料包，不等于收齐所有标准扩展、历次会议提案、论文及商用编码器实现。补充规则见 [收集与版本策略](docs/collection-policy.md)。

算法阅读入口见 [已核对文件存在的源码导航](docs/source-map.md)。硬件分工与 Windows 对照见 [硬件说明](docs/hardware.md)。

## 目录

```text
configs/                 来源清单、模型登记、算法覆盖与 MLX 配置
benchmarks/dev-v1/       四标准开发题、独立答案与评分规则
datasets/pilot-v1/      自写的小批训练候选、证据和核验记录
docs/                    落地、数据、评测、硬件和源码导航
prompts/                 AI 生成与审查提示词
schemas/                 样本格式
scripts/                 收集、提取、证据包、数据校验、拆分与环境检查
materials/sources.lock.json  实际来源锁定记录（纳入 Git）
materials/raw/           下载的 PDF、文档、JM ZIP（本地，Git 忽略）
materials/code/          固定提交的第三方源码（本地，Git 忽略）
materials/extracted/     页级文本及哈希（本地，Git 忽略）
data/                    候选、人工核验与训练数据（默认 Git 忽略）
runs/                    模型、环境与评测运行记录（Git 忽略）
```

## 可执行的准备命令

在仓库根目录运行：

```bash
python3 scripts/doctor.py
python3 scripts/collect_sources.py --include-code
python3 scripts/unpack_jm.py
python3 scripts/build_source_map.py
uv venv --python 3.12 .venv-materials
uv pip install --python .venv-materials/bin/python -r requirements-materials.txt
.venv-materials/bin/python scripts/extract_documents.py
python3 scripts/dev_benchmark.py verify --sources
python3 scripts/verify_pilot_batch.py
python3 -m unittest discover -s tests -v
```

收集脚本只下载与校验资料，不执行下载的代码。锁文件存在时校验原有内容，Git 不自动追随最新分支。复制到另一台电脑后运行收集脚本，可按已锁定提交重新获取源码。

## 当前边界

资料库、数据准备工具、开发评测 v1 与首批训练候选已建立。开发题用于检查流程和比较基座，不能替代独立的最终测试。候选待入训审核，仓库尚无正式训练集，也未记录真实模型推理、微调收益或硬件速度。

下载成功与可公开再分发是不同状态。原文和第三方代码留在本地，逐样本保存来源和使用条件；后续公开数据或模型时保留对应通知。自有文件尚未统一声明开源许可证，避免误覆盖第三方权利。
