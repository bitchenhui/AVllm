# AVllm 独立验收小样本 v2

24 题覆盖 H.264、H.265、H.266、AV1 各 6 题，共 16 道可程序复算的计算题和 8 道有评分点的解释题。保留原来的 8 题，并在四个新机制各增加 4 题：H.264 scaling list 递推、HEVC CABAC 上下文初始化、VVC 虚拟边界坐标、AV1 tile group 长度。数据按机制隔离，不将同组变体视为完全独立的样本。

题面、评分键分别存在评测机的 `data/holdout/v2/`，Git 只保存 [冻结清单](manifest.json)、机制登记和评测代码。授予训练的任何数据不包含这些问答。首轮推理前已固定题面与答案哈希，复算数值答案、核对来源并检查与开发、训练和验证数据在题目、机制、来源定位上的重合。此小样本还未完成独立人工审题，结果用于判断下一阶段优先级。

三组复用同一份 Qwen3-4B-Instruct-2507 4bit 权重、开发机和简洁系统提示：A 只有题面；B 加本地资料检索和整数计算器；D 用扩充数据后的 24 步 LoRA，加与 B 相同的资料和计算器。三组都用贪心解码、seed 42、每题总计最多 384 个生成 token，工具调用的生成计入同一预算。B/D 输入长度和实际调用次数可能不同于 A；B/D 之间资料和工具配置相同。

检索按题面自带的标准类别在本机锁定 PDF 中搜索，对抽取的文本片段用 BM25 排序。查询只用题面文字，不使用评分键、参考页或候选训练答案。计算器只接受受限整数表达式，由模型选择是否调用，最多三次。命中参考页只是检索诊断，不能证明片段包含答案所需的全部条件。

持有隔离题库的评测机可以复跑（在仓库根目录，运行目录须全新）：

```bash
python3 scripts/verify_acceptance.py
python3 scripts/retrieve_acceptance_context.py --output runs/acceptance-v2-replay-contexts
common=(--benchmark data/holdout/v2 --model-dir models/qwen3-4b-mlx-4bit
        --model-id mlx-community/Qwen3-4B-Instruct-2507-4bit
        --revision 50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b
        --system-prompt-file prompts/dev-concise-system.txt --max-tokens 384 --seed 42)
assist=(--contexts runs/acceptance-v2-replay-contexts/contexts.jsonl --calculator)
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
.venv-train/bin/python scripts/dev_benchmark.py run "${common[@]}" --output runs/acceptance-v2-replay-base
.venv-train/bin/python scripts/dev_benchmark.py run "${common[@]}" "${assist[@]}" --output runs/acceptance-v2-replay-assisted
.venv-train/bin/python scripts/dev_benchmark.py run "${common[@]}" "${assist[@]}" \
  --adapter-path runs/phase1-domain-m4pro-boundary-v1/adapter --output runs/acceptance-v2-replay-tuned
python3 scripts/blind_review.py prepare --benchmark data/holdout/v2 \
  --runs runs/acceptance-v2-replay-base runs/acceptance-v2-replay-assisted runs/acceptance-v2-replay-tuned \
  --output runs/acceptance-v2-replay-blind
```

评分员只读取匿名目录里的 `queue.jsonl`，按每条的 `rubric` 为每个回答记录 `id`、`label`、`points`（评分点 ID 映射到 0 或 1）和 `note`，保存为 `ratings.jsonl`。评分完成后再读取映射。运行 `score_acceptance.py`，通过 `--base`、`--assisted`、`--tuned`、`--contexts`、`--review` 和 `--output` 传入目录或输出文件。严格数值分要求指定的单行整数 JSON；数值内容诊断允许完整多行对象，仍拒绝猜数或求值表达式。

11 月 17 日的首次运行见[验收复盘](../../docs/acceptance-2026-11-17.md)。解释题为单评审匿名 AI 评分，不能代替独立领域审核。该组题跑完后继续锁定，不据此改题或选择超参；需要迭代设置时回到开发集。
