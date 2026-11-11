# AV2 与 Beyond VVC 跟踪记录

以下是后续研究的官方入口。第一期训练、验证和评测继续覆盖 AVC、HEVC、VVC、AV1。这些条目不进入核心来源清单，不参与数据导出。

## AV2

- 规范：[AOMedia AV2 官方入口](https://av2.aomedia.org/)，登记版本为 [AV2 Bitstream and Decoding Process Specification v1.0.0](https://av2.aomedia.org/v1.0.0/20260528_38f28e7_AV2_Spec_v1.0.0.pdf)。
- 参考实现：[AVM v1.0.0](https://github.com/AOMediaCodec/avm/releases/tag/v1.0.0)，对应 [966a7d7cd6fcf60360caf5dc413b2aeeb65e144d](https://github.com/AOMediaCodec/avm/commit/966a7d7cd6fcf60360caf5dc413b2aeeb65e144d)。本记录登记来源，未下载或校验本地副本。
- 后续先选 2–3 个可从规范和源码双重核对的机制，编写带版本的检索验证题。分别测基座与带资料检索的回答，重点检查 AV1 与 AV2 的语法和算法是否混淆。确认需求及可核验样本后，再决定是否建独立训练批次。

## Beyond VVC

- 官方入口：[ITU：Beyond VVC 技术提案征集](https://www.itu.int/hub/2026/07/beyond-vvc-call-for-proposals-on-future-video-coding/)。当前按征集与提案跟踪，不把“H.267”作为已发布的标准编号。
- 讨论候选技术时标注提案编号、修订版和日期，区分候选技术与正式规范条款。
