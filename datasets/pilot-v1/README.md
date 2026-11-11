# 四标准训练候选 Pilot v1

每个标准选择一个开发集未使用的机制，各 4 条，共 16 条。每组含 1 道机制解释、2 道数值题和 1 道指定实现的源码题：

- **H.264**：亮度 Intra_4x4_DC 的邻边可用性、舍入与回退。
- **H.265**：基础 HEVC merge 候选上限、索引传输和推断。
- **H.266**：POC 高位的历史回绕与显式周期。
- **AV1**：superres 分母、编码宽度的舍入与高度保持。

`candidates.jsonl` 使用仓库的样本格式；题面和答案是项目自写，源码题采用经过核对的逻辑释义。标准和源码原件不随这个小批提交，候选记录保存对应的来源锁、位置和哈希。源码定位和适用条件见[核验记录](source-review.md)。

`numeric-cases.json` 保存 8 道计算题的输入与独立期望。候选的最后一行有整数 JSON，便于校验。实际计算结果、数据哈希与证据统计见 `verification-report.json`。恢复本地标准文本和固定源码后，可在仓库根目录复验：

```bash
python3 scripts/validate_samples.py datasets/pilot-v1/candidates.jsonl
python3 scripts/verify_pilot_batch.py
```

复验检查样本结构、来源锁、开发集重合和数值答案，不替代专业审阅。源码题经过静态核对，尚无编码/解码实验结论。样本整体 `verification.status` 和 `eligibility.status` 保持 `pending`，不会直接导出为训练数据。

后续由领域审核者确认适用条件及来源使用条件，再把通过的样本放入审核目录。当前四组按分组规则都进入 train；还需要单独的验证机制组才能做首轮导出。此批只用于验证生产和核验流程，不作为最终训练量或能力评测。
