# 本地源码导航

下列文件在固定快照中已检查存在。它们是阅读入口，不表示已逐函数验证算法。标准语义与编码器搜索策略分别解释。

Git 来源的完整提交号及实际 origin 见 `materials/sources.lock.json`；JM 以 ZIP 的 SHA-256 固定。源码与引用行号必须使用同一快照。

## JM

来源 id：`jm-code`；版本锁：`5a87ec1b112423748897fb771f249ac6b7cc8a50c3b56350275857346eed9e1f`

- `materials/code/JM/lencod/src/quant4x4.c`
- `materials/code/JM/lencod/src/quant8x8.c`
- `materials/code/JM/lencod/src/transform8x8.c`
- `materials/code/JM/lencod/src/ratectl.c`
- `materials/code/JM/lencod/src/loopFilter.c`

## x264

来源 id：`x264-code`；版本锁：`0480cb05fa188d37ae87e8f4fd8f1aea3711f7ee`

- `materials/code/x264/common/dct.c`
- `materials/code/x264/common/quant.c`
- `materials/code/x264/common/deblock.c`
- `materials/code/x264/encoder/analyse.c`
- `materials/code/x264/encoder/me.c`
- `materials/code/x264/encoder/rdo.c`
- `materials/code/x264/encoder/ratecontrol.c`

## HM

来源 id：`hm-code`；版本锁：`92d95ddd2995d0ae3149d3dac1e573e96460b821`

- `materials/code/HM/source/Lib/TLibCommon/TComTrQuant.cpp`
- `materials/code/HM/source/Lib/TLibCommon/TComPrediction.cpp`
- `materials/code/HM/source/Lib/TLibEncoder/TEncSearch.cpp`
- `materials/code/HM/source/Lib/TLibEncoder/TEncCu.cpp`

## x265

来源 id：`x265-code`；版本锁：`9bb47b765b438f136364848fd4592fc692a8cf77`

- `materials/code/x265/source/common/quant.cpp`
- `materials/code/x265/source/common/deblock.cpp`
- `materials/code/x265/source/encoder/analysis.cpp`
- `materials/code/x265/source/encoder/motion.cpp`
- `materials/code/x265/source/encoder/ratecontrol.cpp`

## VTM

来源 id：`vtm-code`；版本锁：`010584cf75dd0b61bd6295d7eacf20975094aac4`

- `materials/code/VTM/source/Lib/CommonLib/TrQuant.cpp`
- `materials/code/VTM/source/Lib/CommonLib/QuantRDOQ.cpp`
- `materials/code/VTM/source/Lib/CommonLib/DepQuant.cpp`
- `materials/code/VTM/source/Lib/CommonLib/IntraPrediction.cpp`
- `materials/code/VTM/source/Lib/CommonLib/InterPrediction.cpp`
- `materials/code/VTM/source/Lib/EncoderLib/EncCu.cpp`

## vvenc

来源 id：`vvenc-code`；版本锁：`a455d51e335c97b40eeea7bb90e3ad52b84c6e83`

- `materials/code/vvenc/source/Lib/CommonLib/TrQuant.cpp`
- `materials/code/vvenc/source/Lib/CommonLib/DepQuant.cpp`
- `materials/code/vvenc/source/Lib/CommonLib/IntraPrediction.cpp`
- `materials/code/vvenc/source/Lib/EncoderLib/EncCu.cpp`

## vvdec

来源 id：`vvdec-code`；版本锁：`d2614690cf13ceee1631dd6d30141755b8a689de`

- `materials/code/vvdec/source/Lib/CommonLib/TrQuant.cpp`
- `materials/code/vvdec/source/Lib/CommonLib/IntraPrediction.cpp`
- `materials/code/vvdec/source/Lib/CommonLib/InterPrediction.cpp`

## libaom

来源 id：`libaom-code`；版本锁：`8a1038536cde81c548341145f40d6dfddc3077d6`

- `materials/code/libaom/av1/encoder/rdopt.c`
- `materials/code/libaom/av1/encoder/encodeframe.c`
- `materials/code/libaom/av1/encoder/av1_quantize.c`
- `materials/code/libaom/av1/common/cdef.c`
- `materials/code/libaom/av1/common/restoration.c`

## SVT-AV1

来源 id：`svtav1-code`；版本锁：`e3d63405f9ba8219913a7276c2c47d10e5d022fe`

- `materials/code/SVT-AV1/Docs/svt-av1-encoder-design.md`
- `materials/code/SVT-AV1/Source/Lib/Codec/transforms.c`
- `materials/code/SVT-AV1/Source/Lib/Codec/motion_estimation.c`
- `materials/code/SVT-AV1/Source/Lib/Codec/coding_loop.c`
- `materials/code/SVT-AV1/Source/Lib/Codec/cdef.c`
- `materials/code/SVT-AV1/Source/Lib/Codec/restoration.c`

## dav1d

来源 id：`dav1d-code`；版本锁：`662868772f73be8c055a6aa7e30f222be13a5f65`

- `materials/code/dav1d/src/decode.c`
- `materials/code/dav1d/src/dequant_tables.c`
- `materials/code/dav1d/src/cdef_tmpl.c`
- `materials/code/dav1d/src/looprestoration_tmpl.c`

## av1-spec

来源 id：`av1-spec-source`；版本锁：`4f2ff41559ab4ac241d1957a17e1f1c2814e26d2`

- `materials/code/av1-spec/06.bitstream.syntax.md`
- `materials/code/av1-spec/07.bitstream.semantics.md`
- `materials/code/av1-spec/08.decoding.process.md`
- `materials/code/av1-spec/09.parsing.process.md`
