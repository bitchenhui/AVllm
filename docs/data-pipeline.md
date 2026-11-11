# AI 辅助数据生成与校验

## 1. 先创建证据包

原文页是事实来源，提取文本是检索辅助。先对照 PDF 检查公式、上下标、矩阵、表格和条件，再选择页。例：下面命令取指定 PDF 的第 1 个物理页，只演示包格式；封面不用于制造算法知识样本。

```bash
python3 scripts/make_packet.py --source h264-spec --page 1 --group avc-cover-format-demo --output work/packet-demo.json
```

代码证据可指定相对文件和行号，范围必须真实存在。证据包内保存 source 的文件哈希/提交号、定位信息、抽取片段及片段 SHA-256。`make_packet.py` 输出来源包含 `evidence` 项，可直接用于候选样本。定位页号以 PDF 物理页为准，与纸面章节页码分别记录。

先为机制/函数/实验家族确定 `split_group`，再生成变体；同组所有候选使用一致拆分。已决定用于冻结测试的机制家族写入 `configs/holdout-groups.json` 的 `groups`，禁止进入训练。和开发集机制组或锁定证据重合的包会标为 `dev`；选用其他机制或证据制作训练样本。

## 2. AI 生成候选

将证据包、`prompts/generate.md`、样本格式一起交给教师模型。输出 JSONL，每条样本包含 `id, codecs, topic, task_type, split_group, messages, evidence, generation, verification, eligibility`。生成样本的 `verification.status` 必须为 pending，`eligibility.status` 必须为 pending；生成器不能为自己的答案签发通过状态。

教师只看本单元资料；不提供开发题或冻结评测答案来生成训练样本。每批先生成少量，避免批量复制同一种错误。设计原理、边界、反例、计算、代码解释、跨标准比较等不同任务。证据不足时使用 `insufficient_information`，解释缺失条件，禁止编造条款号或函数名补齐答案。

`generation` 记录教师名、实际版本、提示词版本和时间；无法获取的版本填 unknown，不能编造。教师只是内容生成器，MLX/PyTorch 执行梯度训练。AI 辅助编写脚本不意味着聊天本身会更新模型权重。

## 3. 自动检查与独立核验

```bash
python3 scripts/validate_samples.py data/candidates/batch-001.jsonl
```

脚本检查结构、来源是否存在且已获取、版本锁匹配、证据片段哈希、重复 id/问题、split_group 以及必需核验项。相同来源/版本/片段被放入不同组会被拒绝，需要先合并关联机制家族。它验证可追溯性，不能证明专业结论正确，也不会自动修改 pending 状态。

核验要求：

- 原理/对比/纠错：来源核对 + 条件完整性核对。
- 计算：独立计算脚本，保存输入输出与舍入/溢出规则。教师自算结果不能作为独立检查。
- 源码：检查固定版本的真实代码、上下文、位深/编译路径；涉及改动的任务再做编译与回归。
- 实验：运行真实命令，保存输入序列哈希、编码器提交、构建参数、配置、输出码流哈希和原始指标。无测量结果只能生成实验设计，不能生成“已经改善多少”的结论。

用 `prompts/review.md` 进行第二轮审核；审核 AI 要看到原证据。由领域审核者检查关键题和抽样，确认后填写 `verification.reviewer`、`reviewed_at`、检查结果与对应证据。每个 check 的 artifact 必须指向仓库内真实、非空的审核报告或验证结果文件（推荐放在 work/ 或 runs/）。使用条件也已核对时再将 eligibility 改为 approved。不得为了通过脚本把所有状态批量改成 passed。

## 4. 分组拆分与导出

```bash
python3 scripts/prepare_training.py data/approved/pilot.jsonl --output data/splits/pilot
```

工具先运行严格验证，拒绝开发题 ID、组、题面或锁定证据有重合的样本，再按 split_group 稳定分配 80/10/10；冻结 holdout 组总是 test。输出 MLX `train.jsonl`、`valid.jsonl`、`test.jsonl`，并保留 `provenance.jsonl` 和统计哈希 `manifest.json`。源样本 metadata 不丢失。

同题精确重复会被拒绝，语义重复与隐蔽的家族关联需要另行人工或检索检查。哈希随机划分不是覆盖保证，查看每标准/模块的分布；小数据集可能出现空 split，准备工具会拒绝空训练或验证集。

不能把 test 放进训练数据、检索语料、教师改写材料或学习率选择。新增测试版本时记录变更理由，旧结果保留，不能回填覆盖原始分数。

## 5. 具体的首批工作

已有[四标准各 5 道开发题](../benchmarks/dev-v1/README.md)和[四标准各 4 条训练候选](../datasets/pilot-v1/README.md)，两者分离。先独立复核已核验的候选，按需要补充不同机制的验证样本，完成一次小批导出后再扩大到冻结测试与约 2,000 条候选。
