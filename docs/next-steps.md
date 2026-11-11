# 下一步：先验证开发集，再准备独立训练候选

主训练机是家中 M2 Max 32GB / 1TB。训练机暂不可达时，可以在开发机完成数据准备和推理基线。首轮微调仍待入训审核与训练机环境就绪。

## 现在可以做

1. 阅读 [开发评测 v1](../benchmarks/dev-v1/README.md)。四个标准各 5 道，共 20 道，其中 4 道可自动判定数值，其余按独立评分点复核。题面与答案分别保存，已做来源和数值核对，仍待独立领域复核。
2. 离线检查问题、答案和证据锁：

   ```bash
   python3 scripts/dev_benchmark.py verify --sources
   python3 -m unittest discover -s tests -v
   ```

3. 复验[四标准共 16 条训练候选](../datasets/pilot-v1/README.md)：`python3 scripts/verify_pilot_batch.py`。首批已完成来源、条件、源码静态和数值检查，下一步是独立领域复核及使用条件确认。新增样本时继续按 [数据流水线](data-pipeline.md) 固定证据；`dev` 或 `test` 证据不能用于训练。
4. 复验[8 条独立验证候选](../datasets/validation-v1/README.md)：`python3 scripts/verify_validation_batch.py`。这四组预先注册为 valid，待领域复核后可和训练候选一同作为导出输入。
5. [最终测试草案](../benchmarks/holdout-v1/README.md) 已预留四个机制并锁定 8 题。由独立领域审核者复核题面和评分键后再用于验收；训练和配置选择过程中只用开发及验证集。
6. 阅读已完成的 [M4 Pro 未微调基线与提示对照](dev-baseline.md)。先复核 16 道非数值题，再用不同机制补整数边界、标准条件及源码分支题。比较微调前后时固定系统提示、权重版本与生成预算。

## 训练前检查（2026-11-11）

已使用本地 Qwen3-4B 的真实 tokenizer 和完整聊天模板检查两批候选：[16 条训练候选的长度报告](../datasets/pilot-v1/token-length-report.json)记录合计 2883 token、最长 219 token；[8 条验证候选的报告](../datasets/validation-v1/token-length-report.json)记录合计 1309 token、最长 208 token。全部低于起始配置的 2048 上限。这些总数包含问题、答案和模板标记，不能当作参与 loss 的答案 token 数。

检查时发现 Transformers 5.22.2 默认返回含 input_ids 和 attention_mask 的字典，旧计数方式会误报 2 token。长度脚本现显式取 token ID 列表，并拒绝异常结构；报告记录版本、参数、逐样本长度和 tokenizer 哈希。此前推理基线使用文本 prompt 和 MLX 包装器，不使用这个长度脚本。

另与已安装的 MLX-LM 0.32.2 ChatDataset 做了只读核对：24 条样本的模板长度一致；mask_prompt 开启后均有非空的答案区间。训练候选最短答案区间为 64 token，验证候选为 57 token。当前 24 条的审核及使用条件状态仍为 pending，严格导出检查均正确拒绝，未生成正式训练集。

在仓库根目录可重新检查长度：

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv-train/bin/python scripts/check_token_lengths.py \
  datasets/pilot-v1/candidates.jsonl --tokenizer models/qwen3-4b-mlx-4bit \
  --max-tokens 2048 --report runs/preflight/pilot-token-lengths.json
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv-train/bin/python scripts/check_token_lengths.py \
  datasets/validation-v1/candidates.jsonl --tokenizer models/qwen3-4b-mlx-4bit \
  --max-tokens 2048 --report runs/preflight/validation-token-lengths.json
```

接下来的准备按优先级推进：

1. 开发基线的 16 道非数值题已完成逐点 AI 初审，见[运行记录](dev-baseline.md#后续初审与来源辅助对照)；继续完成独立复核和训练/验证候选的领域审核。
2. 已完成同题带标准/源码的来源辅助对照。先精简完整相关条款，再评估上下文选择；当前来源由开发题证据定位给定，还不是自动检索效果。资料库不包含评测题答案。
3. 从不同机制扩充短答案、边界条件和代码路径样本。现有 16 条训练候选适合流程冒烟，数量和覆盖度不足以评估领域微调收益。
4. 训练机恢复访问后，记录数据、环境及模型版本，先做 100 步冒烟，确认 loss、答案 masking、适配器保存和重载，再测吞吐与峰值内存。

早期四个变换/量化入口仍在 `configs/seed-units.json`。这些是阅读入口。H.264 和 HEVC 两份入口的证据已用于开发集，重新打包会标记为 `dev`。对其余证据也应先查看机制及来源是否与开发题相近。

## 训练机恢复访问后

1. 获取包含本开发集的仓库版本，运行 `scripts/doctor.py`；按锁文件恢复资料和源码。单独 Git 同步不包含本地原件、提取文本、模型和语料。
2. 按 [Mac 微调指南](mac-training.md) 准备 Python 环境和候选模型。先按 [基线命令](../benchmarks/dev-v1/README.md#模型准备好后) 跑未微调模型。基座比较使用同一题目和生成预算，把开发分数用于排错及筛选。
3. 核验训练候选和冻结测试后做 100 步冒烟；记录峰值内存与吞吐。随后用同一基座、同样的检索结果比较微调前后。第一期不凭开发集或训练 loss 宣称最终效果。
