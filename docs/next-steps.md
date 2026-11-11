# 下一步：先验证开发集，再准备独立训练候选

主训练机是家中 M2 Max 32GB / 1TB。训练机暂不可达时，可以在开发机完成数据和评测准备。仓库仍没有真实模型成绩或微调结果。

## 现在可以做

1. 阅读 [开发评测 v1](../benchmarks/dev-v1/README.md)。四个标准各 5 道，共 20 道，其中 4 道可自动判定数值，其余按独立评分点复核。题面与答案分别保存，已做来源和数值核对，仍待独立领域复核。
2. 离线检查问题、答案和证据锁：

   ```bash
   python3 scripts/dev_benchmark.py verify --sources
   python3 -m unittest discover -s tests -v
   ```

3. 复验[四标准共 16 条训练候选](../datasets/pilot-v1/README.md)：`python3 scripts/verify_pilot_batch.py`。首批已完成来源、条件、源码静态和数值检查，下一步是独立领域复核及使用条件确认。新增样本时继续按 [数据流水线](data-pipeline.md) 固定证据；`dev` 或 `test` 证据不能用于训练。
4. 为最终测试单独保留一批机制与实验家族，在 `configs/holdout-groups.json` 的 `groups` 登记。不要把开发题改写后当作冻结测试；开发题和已见到的答案也不能进入训练或检索语料。

早期四个变换/量化入口仍在 `configs/seed-units.json`。这些是阅读入口。H.264 和 HEVC 两份入口的证据已用于开发集，重新打包会标记为 `dev`。对其余证据也应先查看机制及来源是否与开发题相近。

## 训练机恢复访问后

1. 获取包含本开发集的仓库版本，运行 `scripts/doctor.py`；按锁文件恢复资料和源码。单独 Git 同步不包含本地原件、提取文本、模型和语料。
2. 按 [Mac 微调指南](mac-training.md) 准备 Python 环境和候选模型。先按 [基线命令](../benchmarks/dev-v1/README.md#模型准备好后) 跑未微调模型。基座比较使用同一题目和生成预算，把开发分数用于排错及筛选。
3. 核验训练候选和冻结测试后做 100 步冒烟；记录峰值内存与吞吐。随后用同一基座、同样的检索结果比较微调前后。第一期不凭开发集或训练 loss 宣称最终效果。
