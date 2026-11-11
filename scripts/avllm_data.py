"""Shared evidence and fail-closed dataset utilities (standard library only)."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CODECS = {"h264", "h265", "h266", "av1"}
TASKS = {"explanation", "comparison", "calculation", "source_code", "experiment_design",
         "experiment_analysis", "misconception", "insufficient_information"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def normalized(text):
    return re.sub(r"\s+", " ", text).strip().casefold()


def split_for(group, holdouts=()):
    if group in holdouts:
        return "test"
    bucket = int(sha(("avllm-phase1-v1|" + group).encode())[:8], 16) % 100
    return "train" if bucket < 80 else "valid" if bucket < 90 else "test"


def read_jsonl(path):
    rows = []
    with Path(path).open() as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{i}: invalid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{i}: expected object")
            rows.append(row)
    if not rows:
        raise ValueError("Dataset contains no samples")
    return rows


def bounded_path(base, relative):
    target = (base / relative).resolve()
    if base.resolve() not in target.parents:
        raise ValueError("Evidence path escapes source root")
    return target


def selected_lines(text, locator):
    start, end = locator.get("start"), locator.get("end")
    if type(start) is not int or type(end) is not int or not 1 <= start <= end:
        raise ValueError("Line range must be positive integers, end >= start")
    lines = text.splitlines()
    if end > len(lines):
        raise ValueError(f"Line range exceeds file ({len(lines)} lines)")
    return "\n".join(lines[start - 1:end])


def evidence_text(source, locator, root=ROOT):
    path = bounded_path(root, source["path"])
    if source.get("status") != "collected":
        raise ValueError("Source was not successfully collected")
    if source["kind"] == "git":
        current = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
        if current != source["commit"]:
            raise ValueError("Git checkout differs from locked revision")
        if subprocess.check_output(["git", "-C", str(path), "status", "--porcelain"], text=True).strip():
            raise ValueError("Git evidence checkout has local changes")
    elif sha(path.read_bytes()) != source["sha256"]:
        raise ValueError("Source file differs from locked SHA-256")
    kind = locator.get("type")
    if kind == "pdf_page" and source["kind"] == "pdf":
        page = locator.get("page")
        if type(page) is not int or page < 1:
            raise ValueError("PDF page must be a positive integer")
        extracted = root / "materials/extracted" / source["id"]
        metadata = json.loads((extracted / "metadata.json").read_text())
        if metadata["source_sha256"] != source["sha256"]:
            raise ValueError("PDF extraction is stale")
        for line in (extracted / "pages.jsonl").open():
            item = json.loads(line)
            if item["pdf_page"] == page:
                if sha(item["text"].encode()) != item["text_sha256"]:
                    raise ValueError("Extracted page text hash mismatch")
                return item["text"]
        raise ValueError("Requested PDF page does not exist")
    if kind == "file_lines" and source["kind"] == "git":
        return selected_lines(bounded_path(path, locator["path"]).read_text(), locator)
    if kind == "document_lines" and source["kind"] in {"text", "html"}:
        if source["kind"] == "text":
            text = path.read_text()
        else:
            extracted = root / "materials/extracted" / source["id"]
            metadata = json.loads((extracted / "metadata.json").read_text())
            if metadata["source_sha256"] != source["sha256"]:
                raise ValueError("HTML extraction is stale")
            text = (extracted / "document.txt").read_text()
        return selected_lines(text, locator)
    if kind == "archive_lines" and source["kind"] == "archive":
        with zipfile.ZipFile(path) as archive:
            text = archive.read(locator["path"]).decode("utf-8", errors="replace")
        return selected_lines(text, locator)
    raise ValueError("Locator type is incompatible with source kind")


def validate(rows, require_approved=False, root=ROOT):
    lock = json.loads((root / "materials/sources.lock.json").read_text())
    sources = {x["id"]: x for x in lock["sources"]}
    errors, seen_ids, seen_questions, evidence_groups, evidence_cache = [], set(), set(), {}, {}
    required = {"id", "codecs", "topic", "task_type", "split_group", "messages", "evidence",
                "generation", "verification", "eligibility"}
    for n, row in enumerate(rows, 1):
        label = f"row {n} ({row.get('id', '?')})"
        try:
            if set(row) != required:
                raise ValueError(f"Expected exact top-level fields; missing={required-set(row)}, extra={set(row)-required}")
            for key in ("id", "topic", "split_group"):
                if not isinstance(row[key], str) or not row[key].strip():
                    raise ValueError(f"{key} must be nonempty text")
            if row["id"] in seen_ids:
                raise ValueError("Duplicate sample id")
            seen_ids.add(row["id"])
            codecs = row["codecs"]
            if not isinstance(codecs, list) or not codecs or any(x not in CODECS for x in codecs) or len(set(codecs)) != len(codecs):
                raise ValueError("Invalid codecs")
            if row["task_type"] not in TASKS:
                raise ValueError("Invalid task_type")
            msgs = row["messages"]
            if not isinstance(msgs, list) or len(msgs) < 2 or any(not isinstance(m, dict) for m in msgs):
                raise ValueError("At least a user and assistant message are required")
            for m in msgs:
                if set(m) != {"role", "content"} or m["role"] not in {"system", "user", "assistant"} or not isinstance(m["content"], str) or not m["content"].strip():
                    raise ValueError("Invalid chat message")
            roles = [m["role"] for m in msgs]
            dialogue = roles[1:] if roles[0] == "system" else roles
            if dialogue != ["user" if i % 2 == 0 else "assistant" for i in range(len(dialogue))] or dialogue[-1] != "assistant":
                raise ValueError("Chat must alternate user/assistant after an optional initial system message")
            question = normalized("\n".join(m["content"] for m in msgs if m["role"] == "user"))
            if question in seen_questions:
                raise ValueError("Duplicate normalized user question/context")
            seen_questions.add(question)
            evidences = row["evidence"]
            if not isinstance(evidences, list) or not evidences:
                raise ValueError("At least one evidence locator is required")
            supported = set()
            for ev in evidences:
                if set(ev) != {"source_id", "source_revision", "locator", "snippet_sha256"}:
                    raise ValueError("Invalid evidence fields")
                source = sources.get(ev["source_id"])
                if source is None:
                    raise ValueError("Unknown source id")
                if ev["source_revision"] != source.get("commit", source.get("sha256")):
                    raise ValueError("Evidence revision differs from source lock")
                locator = ev["locator"]
                if not isinstance(locator, dict):
                    raise ValueError("Evidence locator must be an object")
                locator_fields = {"pdf_page": {"type", "page"}, "file_lines": {"type", "path", "start", "end"},
                                  "document_lines": {"type", "start", "end"}, "archive_lines": {"type", "path", "start", "end"}}
                if set(locator) != locator_fields.get(locator.get("type"), set()):
                    raise ValueError("Invalid fields for locator type")
                cache_key = (source["id"], ev["source_revision"], json.dumps(locator, sort_keys=True))
                if cache_key not in evidence_cache:
                    text = evidence_text(source, locator, root)
                    evidence_cache[cache_key] = sha(text.encode()) if text.strip() else None
                if ev["snippet_sha256"] != evidence_cache[cache_key] or evidence_cache[cache_key] is None:
                    raise ValueError("Evidence snippet hash differs or evidence is empty")
                fingerprint = (ev["source_id"], ev["source_revision"], ev["snippet_sha256"])
                if fingerprint in evidence_groups and evidence_groups[fingerprint] != row["split_group"]:
                    raise ValueError("Identical evidence is assigned to different split groups; merge the mechanism families before splitting")
                evidence_groups[fingerprint] = row["split_group"]
                supported.add(source["codec"])
            if len(codecs) > 1 and not set(codecs).issubset(supported) and "shared" not in supported:
                raise ValueError("Cross-codec sample lacks evidence covering its codecs")
            gen = row["generation"]
            if set(gen) != {"model", "revision", "prompt_version", "created_at"} or any(not isinstance(x, str) or not x.strip() for x in gen.values()):
                raise ValueError("Missing generation provenance")
            ver = row["verification"]
            if set(ver) != {"status", "checks", "reviewer", "reviewed_at"} or ver["status"] not in {"pending", "passed", "failed"} or not isinstance(ver["checks"], list):
                raise ValueError("Invalid verification record")
            if any(value is not None and not isinstance(value, str) for value in (ver["reviewer"], ver["reviewed_at"])):
                raise ValueError("Reviewer and reviewed_at must be text or null")
            checks = ver["checks"]
            for check in checks:
                if set(check) != {"kind", "result", "artifact"} or check["kind"] not in {"evidence", "conditions", "calculation", "code", "experiment"} or check["result"] not in {"passed", "failed", "pending"} or not isinstance(check["artifact"], str) or not check["artifact"].strip():
                    raise ValueError("Invalid verification check")
            eligibility = row["eligibility"]
            if set(eligibility) != {"status", "note"} or eligibility["status"] not in {"pending", "approved", "rejected"} or not isinstance(eligibility["note"], str) or not eligibility["note"].strip():
                raise ValueError("Invalid eligibility record")
            if require_approved or ver["status"] == "passed":
                if ver["status"] != "passed" or not ver["reviewer"] or not ver["reviewed_at"]:
                    raise ValueError("Reviewed verification required")
                required_checks = {"evidence", "conditions"}
                required_checks |= {"calculation"} if row["task_type"] == "calculation" else set()
                required_checks |= {"code"} if row["task_type"] == "source_code" else set()
                required_checks |= {"experiment"} if row["task_type"] == "experiment_analysis" else set()
                passed = {c["kind"] for c in checks if c["result"] == "passed"}
                if not required_checks.issubset(passed) or any(c["result"] != "passed" for c in checks):
                    raise ValueError("Missing/failed/pending required independent checks")
                for check in checks:
                    artifact = bounded_path(root, check["artifact"])
                    if not artifact.is_file() or artifact.stat().st_size == 0:
                        raise ValueError("Verification artifact must be an existing, nonempty file inside the repository")
            if require_approved and eligibility["status"] != "approved":
                raise ValueError("Eligibility is not approved")
        except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as exc:
            errors.append(f"{label}: {exc}")
    return errors
