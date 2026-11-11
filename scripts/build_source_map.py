#!/usr/bin/env python3
"""Build a verified file-level navigation map and preserve top-level license notices."""
import json
from pathlib import Path
import shutil
import zipfile
from avllm_data import ROOT


ENTRIES = {
    "jm-code": ("JM", ["lencod/src/quant4x4.c", "lencod/src/quant8x8.c", "lencod/src/transform8x8.c", "lencod/src/ratectl.c", "lencod/src/loopFilter.c"]),
    "x264-code": ("x264", ["common/dct.c", "common/quant.c", "common/deblock.c", "encoder/analyse.c", "encoder/me.c", "encoder/rdo.c", "encoder/ratecontrol.c"]),
    "hm-code": ("HM", ["source/Lib/TLibCommon/TComTrQuant.cpp", "source/Lib/TLibCommon/TComPrediction.cpp", "source/Lib/TLibEncoder/TEncSearch.cpp", "source/Lib/TLibEncoder/TEncCu.cpp"]),
    "x265-code": ("x265", ["source/common/quant.cpp", "source/common/deblock.cpp", "source/encoder/analysis.cpp", "source/encoder/motion.cpp", "source/encoder/ratecontrol.cpp"]),
    "vtm-code": ("VTM", ["source/Lib/CommonLib/TrQuant.cpp", "source/Lib/CommonLib/QuantRDOQ.cpp", "source/Lib/CommonLib/DepQuant.cpp", "source/Lib/CommonLib/IntraPrediction.cpp", "source/Lib/CommonLib/InterPrediction.cpp", "source/Lib/EncoderLib/EncCu.cpp"]),
    "vvenc-code": ("vvenc", ["source/Lib/CommonLib/TrQuant.cpp", "source/Lib/CommonLib/DepQuant.cpp", "source/Lib/CommonLib/IntraPrediction.cpp", "source/Lib/EncoderLib/EncCu.cpp"]),
    "vvdec-code": ("vvdec", ["source/Lib/CommonLib/TrQuant.cpp", "source/Lib/CommonLib/IntraPrediction.cpp", "source/Lib/CommonLib/InterPrediction.cpp"]),
    "libaom-code": ("libaom", ["av1/encoder/rdopt.c", "av1/encoder/encodeframe.c", "av1/encoder/av1_quantize.c", "av1/common/cdef.c", "av1/common/restoration.c"]),
    "svtav1-code": ("SVT-AV1", ["Docs/svt-av1-encoder-design.md", "Source/Lib/Codec/transforms.c", "Source/Lib/Codec/motion_estimation.c", "Source/Lib/Codec/coding_loop.c", "Source/Lib/Codec/cdef.c", "Source/Lib/Codec/restoration.c"]),
    "dav1d-code": ("dav1d", ["src/decode.c", "src/dequant_tables.c", "src/cdef_tmpl.c", "src/looprestoration_tmpl.c"]),
    "av1-spec-source": ("av1-spec", ["06.bitstream.syntax.md", "07.bitstream.semantics.md", "08.decoding.process.md", "09.parsing.process.md"])
}


def main():
    sources = {s["id"]: s for s in json.loads((ROOT / "materials/sources.lock.json").read_text())["sources"]}
    lines = ["# 本地源码导航", "", "下列文件在固定快照中已检查存在。它们是阅读入口，不表示已逐函数验证算法。标准语义与编码器搜索策略分别解释。", "",
             "Git 来源的完整提交号及实际 origin 见 `materials/sources.lock.json`；JM 以 ZIP 的 SHA-256 固定。源码与引用行号必须使用同一快照。", ""]
    mapping = []
    for sid, (folder, files) in ENTRIES.items():
        source = sources[sid]
        base = ROOT / "materials/code" / folder
        revision = source.get("commit", source.get("sha256"))
        lines += [f"## {folder}", "", f"来源 id：`{sid}`；版本锁：`{revision}`", ""]
        for name in files:
            path = base / name
            if not path.is_file():
                raise FileNotFoundError(f"Navigation target missing: {path}")
            lines.append(f"- `{path.relative_to(ROOT)}`")
        lines.append("")
        mapping.append({"source_id": sid, "revision": revision, "directory": str(base.relative_to(ROOT)), "files": files})
        licenses = [p for p in base.iterdir() if p.is_file() and any(word in p.name.lower() for word in ("license", "copying", "patent", "copyright"))]
        for path in licenses:
            out = ROOT / "materials/licenses" / sid / path.name
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, out)
    (ROOT / "docs/source-map.md").write_text("\n".join(lines))
    (ROOT / "materials/code-map.json").write_text(json.dumps({"entries": mapping}, ensure_ascii=False, indent=2) + "\n")
    print(f"Verified {sum(len(x['files']) for x in mapping)} navigation files from {len(mapping)} source snapshots")


if __name__ == "__main__":
    main()
