#!/usr/bin/env python3
"""Extract page-level text and evidence hashes. Does not certify factual correctness."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.ignored += 1
        if tag in {"p", "div", "li", "h1", "h2", "h3", "pre", "br", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.ignored = max(0, self.ignored - 1)

    def handle_data(self, data):
        if not self.ignored:
            self.parts.append(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*")
    args = parser.parse_args()
    lock = json.loads((ROOT / "materials/sources.lock.json").read_text())
    records = []
    for source in lock["sources"]:
        if source["status"] != "collected" or source["kind"] not in {"pdf", "text", "html"}:
            continue
        if args.only is not None and source["id"] not in args.only:
            continue
        path = ROOT / source["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError(f"Source hash mismatch: {source['id']}")
        target = ROOT / "materials/extracted" / source["id"]
        target.mkdir(parents=True, exist_ok=True)
        metadata = {"source_id": source["id"], "source_sha256": source["sha256"],
                    "version": source["version"], "extraction_verified": False,
                    "warning": "PDF formulas, tables and diagrams require visual/manual verification before training."}
        if source["kind"] == "pdf":
            try:
                from pypdf import PdfReader
            except ImportError:
                parser.error("Install requirements-materials.txt in a virtual environment (pypdf is required)")
            reader = PdfReader(path)
            metadata.update(pdf_pages=len(reader.pages), pdf_metadata={str(k): str(v) for k, v in (reader.metadata or {}).items()})
            texts = []
            with (target / "pages.jsonl").open("w") as out:
                for i, page in enumerate(reader.pages):
                    text = page.extract_text() or ""
                    label = reader.page_labels[i] if reader.page_labels else str(i + 1)
                    entry = {"source_id": source["id"], "pdf_page": i + 1, "page_label": label,
                             "text_sha256": hashlib.sha256(text.encode()).hexdigest(), "text": text}
                    out.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    texts.append(f"\n\n[PDF page {i + 1}; label {label}]\n{text}")
            (target / "document.txt").write_text("".join(texts))
        else:
            text = path.read_text(errors="replace")
            if source["kind"] == "html":
                extractor = TextExtractor()
                extractor.feed(text)
                text = "".join(extractor.parts)
            (target / "document.txt").write_text(text)
        metadata["text_bytes"] = (target / "document.txt").stat().st_size
        (target / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
        records.append(metadata)
        print(source["id"], metadata.get("pdf_pages", "text"), metadata["text_bytes"], flush=True)
    # Rebuild index from all existing extraction metadata, including earlier --only runs.
    items = [json.loads(p.read_text()) for p in sorted((ROOT / "materials/extracted").glob("*/metadata.json"))]
    (ROOT / "materials/extraction-index.json").write_text(json.dumps({"sources": items}, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
