import copy
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from avllm_data import bounded_path, sha, split_for, validate
import prepare_training


class DataGuards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "materials").mkdir()
        (self.root / "work").mkdir()
        (self.root / "materials/source.txt").write_text("Example evidence.\nCondition: fixture only.\n")
        (self.root / "work/review.md").write_text("Fixture audit record; not a real domain review.")
        source = {"id":"fixture","kind":"text","codec":"h264","path":"materials/source.txt",
                  "status":"collected","sha256":sha((self.root / "materials/source.txt").read_bytes())}
        (self.root / "materials/sources.lock.json").write_text(json.dumps({"sources":[source]}))
        self.row = {
            "id":"fixture-1","codecs":["h264"],"topic":"fixture","task_type":"explanation",
            "split_group":"fixture-family","messages":[{"role":"user","content":"Fixture question?"},{"role":"assistant","content":"Fixture answer."}],
            "evidence":[{"source_id":"fixture","source_revision":source["sha256"],
                         "locator":{"type":"document_lines","start":1,"end":1},"snippet_sha256":sha(b"Example evidence.")}],
            "generation":{"model":"test-fixture","revision":"fixture","prompt_version":"test","created_at":"2026-11-11"},
            "verification":{"status":"pending","checks":[],"reviewer":None,"reviewed_at":None},
            "eligibility":{"status":"pending","note":"Fixture only"}}

    def tearDown(self):
        self.temp.cleanup()

    def approve(self, row):
        row["verification"] = {"status":"passed","checks":[{"kind":k,"result":"passed","artifact":"work/review.md"} for k in ["evidence","conditions"]],
                               "reviewer":"fixture-reviewer","reviewed_at":"2026-11-11"}
        row["eligibility"] = {"status":"approved","note":"Fixture only"}

    def test_candidates_do_not_enter_training(self):
        self.assertEqual(validate([self.row], root=self.root), [])
        self.assertTrue(validate([self.row], require_approved=True, root=self.root))
        self.approve(self.row)
        self.assertEqual(validate([self.row], require_approved=True, root=self.root), [])

    def test_changed_raw_file_is_rejected(self):
        (self.root / "materials/source.txt").write_text("Changed source after locking.")
        self.assertTrue(validate([self.row], root=self.root))

    def test_unknown_source_and_forged_excerpt_are_rejected(self):
        row = copy.deepcopy(self.row)
        row["evidence"][0]["source_id"] = "invented"
        self.assertTrue(validate([row], root=self.root))
        self.row["evidence"][0]["snippet_sha256"] = "0" * 64
        self.assertTrue(validate([self.row], root=self.root))

    def test_duplicate_rewording_whitespace_is_rejected(self):
        other = copy.deepcopy(self.row)
        other["id"] = "fixture-2"
        other["split_group"] = "another-family"
        other["messages"][0]["content"] = "  FIXTURE   question?  "
        self.assertTrue(validate([self.row, other], root=self.root))

    def test_numeric_task_needs_independent_check(self):
        self.approve(self.row)
        self.row["task_type"] = "calculation"
        self.assertTrue(validate([self.row], require_approved=True, root=self.root))
        self.row["verification"]["checks"].append({"kind":"calculation","result":"passed","artifact":"work/review.md"})
        self.assertEqual(validate([self.row], require_approved=True, root=self.root), [])

    def test_shared_evidence_cannot_cross_family_groups(self):
        other = copy.deepcopy(self.row)
        other["id"] = "fixture-2"
        other["split_group"] = "another-family"
        other["messages"][0]["content"] = "A different question from the same evidence?"
        self.assertTrue(validate([self.row, other], root=self.root))
        other["split_group"] = self.row["split_group"]
        self.assertEqual(validate([self.row, other], root=self.root), [])

    def test_claimed_check_requires_real_artifact(self):
        self.approve(self.row)
        self.row["verification"]["checks"][0]["artifact"] = "work/invented.json"
        self.assertTrue(validate([self.row], require_approved=True, root=self.root))

    def test_cross_codec_requires_corresponding_evidence(self):
        self.row["codecs"] = ["h264", "av1"]
        self.assertTrue(validate([self.row], root=self.root))

    def test_group_isolation_and_reserved_holdout(self):
        self.assertEqual(split_for("same-mechanism"), split_for("same-mechanism"))
        self.assertEqual(split_for("same-mechanism", {"same-mechanism"}), "test")
        result = {split_for("independent-family-" + str(i)) for i in range(200)}
        self.assertEqual(result, {"train", "valid", "test"})

    def test_path_escape_is_rejected(self):
        with self.assertRaises(ValueError):
            bounded_path(self.root, "../outside")

    def test_export_preserves_provenance_and_group_isolation(self):
        texts = ["First independent evidence.", "Second independent evidence.", "Third independent evidence."]
        source_path = self.root / "materials/source.txt"
        source_path.write_text("\n".join(texts) + "\n")
        lock_path = self.root / "materials/sources.lock.json"
        lock = json.loads(lock_path.read_text())
        revision = sha(source_path.read_bytes())
        lock["sources"][0]["sha256"] = revision
        lock_path.write_text(json.dumps(lock))
        (self.root / "configs").mkdir()
        (self.root / "configs/holdout-groups.json").write_text(json.dumps({"groups":[]}))
        rows = []
        for i, wanted in enumerate(["train", "valid", "test"]):
            group = next(f"family-{n}" for n in range(10000) if split_for(f"family-{n}") == wanted)
            row = copy.deepcopy(self.row)
            row.update(id=f"fixture-{i}", split_group=group)
            row["messages"][0]["content"] = f"Independent fixture question {i}?"
            row["evidence"][0].update(source_revision=revision, locator={"type":"document_lines","start":i+1,"end":i+1}, snippet_sha256=sha(texts[i].encode()))
            self.approve(row)
            rows.append(row)
        dataset = self.root / "work/fixtures.jsonl"
        dataset.write_text("".join(json.dumps(x) + "\n" for x in rows))
        out = self.root / "work/export"
        with mock.patch.object(prepare_training, "ROOT", self.root), mock.patch.object(sys, "argv", ["prepare_training",str(dataset),"--output",str(out)]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(prepare_training.main(), 0)
        manifest = json.loads((out / "manifest.json").read_text())
        self.assertEqual([manifest["splits"][s]["samples"] for s in ["train","valid","test"]],[1,1,1])
        provenance = [json.loads(line) for line in (out / "provenance.jsonl").read_text().splitlines()]
        self.assertEqual({x["sample"]["id"] for x in provenance}, {x["id"] for x in rows})
        self.assertEqual(manifest["verification_artifact_sha256"]["work/review.md"], sha((self.root / "work/review.md").read_bytes()))

    def test_export_blocks_development_evidence_even_with_changed_question_and_group(self):
        benchmark = self.root / "benchmarks"
        benchmark.mkdir()
        dev = {"id": "dev-fixture", "split_group": "dev-mechanism",
               "prompt": "Independent dev prompt.", "evidence": self.row["evidence"]}
        (benchmark / "questions.jsonl").write_text(json.dumps(dev) + "\n")
        (benchmark / "manifest.json").write_text(json.dumps(
            {"questions_sha256": sha((benchmark / "questions.jsonl").read_bytes())}))
        (self.root / "configs").mkdir()
        (self.root / "configs/holdout-groups.json").write_text(json.dumps(
            {"groups": [], "dev_benchmarks": ["benchmarks/questions.jsonl"]}))
        self.approve(self.row)
        dataset = self.root / "work/approved.jsonl"
        dataset.write_text(json.dumps(self.row) + "\n")
        output = self.root / "work/should-not-exist"
        err = io.StringIO()
        with mock.patch.object(prepare_training, "ROOT", self.root), mock.patch.object(
            sys, "argv", ["prepare_training", str(dataset), "--output", str(output)]
        ), contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as failure:
            prepare_training.main()
        self.assertEqual(failure.exception.code, 1)
        self.assertIn("development benchmark overlap (locked evidence)", err.getvalue())
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
