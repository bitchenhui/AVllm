# 下一步：先建立第一批可核验样本

主训练机已确定为家中 M2 Max 32GB / 1TB；当前设备是 M4 Pro 24GB。先复用已有设备，正式训练用时尚未测量，不需要先购买新 Mac mini。

## 现在已经具备

35项资料的本地原件/源码与来源锁；四标准2813页文本；11组源码/规范源文件的53个已核对存在的阅读入口；候选模型的真实revision；AI提示词；候选审核和拆分工具；两份尚未训练验证的MLX配置。

## 第一个工作单元

选择“变换、量化与重建”作为第一批证据整理专题，四标准同步参与。已经定位的真实入口记录在 `configs/seed-units.json`：

- AVC：`h264-spec`，PDF物理第203页，8.5.1。
- HEVC：`h265-spec`，PDF物理第194页，8.6.2。
- VVC：`h266-spec`，PDF物理第342页，8.7.2。
- AV1：`av1-spec-pdf`，PDF物理第308页，7.13。

这些只是入口，不是完整算法证据包。阅读完整条款、前置条件和引用依赖，对照 `docs/source-map.md` 中相应实现。先生成四份pending证据包：

```bash
python3 scripts/make_packet.py --source h264-spec --page 203 --group avc-transform-decoding-family --output work/packets/h264-transform.json
python3 scripts/make_packet.py --source h265-spec --page 194 --group hevc-scaling-transform-family --output work/packets/h265-transform.json
python3 scripts/make_packet.py --source h266-spec --page 342 --group vvc-scaling-transform-family --output work/packets/h266-transform.json
python3 scripts/make_packet.py --source av1-spec-pdf --page 308 --group av1-inverse-transform-family --output work/packets/av1-transform.json
```

这四条命令已在当前环境运行过；它们不发起模型调用，不更新模型权重。

## 如何开始使用 AI

将一份证据包、`prompts/generate.md` 和 `schemas/sample.schema.json` 提供给教师模型，先生成3–5条pending候选。保留包中assigned_split：当前HEVC示例组分到test，只能生成评测候选；其他包也按实际分组用途处理，不能将test材料转入训练。补齐算法条件后，每标准整理5道人工核验题，总计20道，跑通格式校验和外部数值核验。不要因为自动校验通过就把领域答案视为真。

先冻结独立评测家族，再扩大训练候选。提示词、生成模型和校验结果全部记录；本轮没有自动调用教师服务，也没有创建虚假的approved训练样本。

## 转移到 M2 Max

可以拷贝整个AVllm目录（含本地materials），或先将自有项目文件保存到目标机器，再按锁文件运行收集、JM解包、文档提取和代码导航命令。单独Git同步不会带上被忽略的PDF、源码、模型和语料。迁移后先运行 `scripts/doctor.py`，再按 `docs/mac-training.md` 建立独立Python3.12环境。

准备好审核数据后才下载固定revision的模型，先100步冒烟，再记录吞吐与峰值内存。之后再决定是否用5060笔记本做同条件CUDA对照，以及是否有必要购买新硬件。
