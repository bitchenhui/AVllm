import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import dev_benchmark as bench


class DevBenchmark(unittest.TestCase):
    def test_reference_values_and_manifest(self):
        manifest, questions = bench.load_questions()
        keys = bench.load_key(manifest, questions)
        self.assertEqual(manifest["codec_counts"], {"h264": 5, "h265": 5, "h266": 5, "av1": 5})
        cases = [k["numeric"] for k in keys.values() if k["numeric"] is not None]
        self.assertEqual(len(cases), 4)
        for case in cases:
            self.assertEqual(bench.reference_numeric(case), case["expected"])

    def test_numeric_scoring_distinguishes_ambiguity_from_wrong_values(self):
        self.assertEqual(bench.numeric_result('解释。\n{"n":2,"n":1}', {"n": 1}), "unparseable")
        self.assertEqual(bench.numeric_result('{"n":true}', {"n": 1}), "unparseable")
        self.assertEqual(bench.numeric_result('{"n":2}', {"n": 1}), "incorrect")
        self.assertEqual(bench.numeric_result('结果如下。\n```json\n{"n":1}\n```', {"n": 1}), "correct")

    def test_inference_path_can_run_with_questions_only(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            model = path / "model"
            model.mkdir()
            (model / "config.json").write_text("{}")
            (model / "model.safetensors").write_bytes(b"fixture, not real model weights")
            manifest, questions = bench.load_questions()
            rendered = []

            def chat_template(messages, **kwargs):
                self.assertEqual([m["role"] for m in messages], ["system", "user"])
                rendered.append(messages[1]["content"])
                return messages[1]["content"]

            mlx, core = ModuleType("mlx"), ModuleType("mlx.core")
            mlx.core = core
            core.random = SimpleNamespace(seed=mock.Mock())
            lm, utils = ModuleType("mlx_lm"), ModuleType("mlx_lm.sample_utils")
            lm.load = mock.Mock(return_value=(object(), SimpleNamespace(apply_chat_template=chat_template)))
            lm.stream_generate = lambda *a, **k: iter([
                SimpleNamespace(text="fixture answer", prompt_tokens=7, generation_tokens=2, finish_reason="stop")])
            utils.make_sampler = mock.Mock(return_value=object())
            args = SimpleNamespace(model_dir=model, adapter_path=None, contexts=None, max_tokens=384,
                                   output=path / "run", model_id="fixture", revision="fixture", seed=42)
            with mock.patch.dict(sys.modules, {"mlx": mlx, "mlx.core": core, "mlx_lm": lm,
                                               "mlx_lm.sample_utils": utils}), mock.patch.object(
                bench.importlib.metadata, "version", return_value="fixture"
            ), mock.patch.object(bench, "load_key", side_effect=AssertionError("inference loaded answer key")), contextlib.redirect_stdout(io.StringIO()):
                bench.run(args)
            lm.load.assert_called_once()
            self.assertEqual(rendered, [q["prompt"] for q in questions.values()])
            saved = json.loads((args.output / "manifest.json").read_text())
            self.assertEqual(saved["status"], "completed")
            self.assertEqual(saved["questions_sha256"], manifest["questions_sha256"])

    def test_scoring_review_round_trip_and_prediction_integrity(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            manifest, questions = bench.load_questions()
            answers = {"h264-02": '{"slice_qpy":23}',
                       "h265-02": '{"qp_bd_offset_y":12,"min_slice_qpy":-10,"max_slice_qpy":51}',
                       "h266-02": "QpY 是 -10，QpPrimeY 是 2。",
                       "av1-02": '{"uv_sec_strength":2,"y_sec_strength":4}'}
            predictions = path / "predictions.jsonl"
            predictions.write_text("".join(json.dumps({"id": qid, "answer": answers.get(qid, "fixture")}) + "\n"
                                           for qid in questions))
            bench.write_json(path / "manifest.json", {"status": "completed", "questions_sha256": manifest["questions_sha256"],
                                                       "predictions_sha256": bench.file_sha(predictions)})
            args = SimpleNamespace(run_dir=path)
            with contextlib.redirect_stdout(io.StringIO()):
                bench.score(args)
            scores = json.loads((path / "scores.json").read_text())
            self.assertEqual(scores["overall"]["numeric_correct"], 2)
            self.assertEqual(scores["overall"]["numeric_incorrect"], 1)
            self.assertEqual(scores["overall"]["numeric_unparseable"], 1)
            self.assertEqual(scores["overall"]["manual_points_graded"], 0)
            review = path / "manual-review.jsonl"
            reviews = [json.loads(row) for row in review.read_text().splitlines()]
            self.assertEqual(len(reviews), 16)
            reviews[0]["ratings"].update(p1=1, p2=0)
            review.write_text("".join(json.dumps(row) + "\n" for row in reviews))
            review_before = review.read_bytes()
            with contextlib.redirect_stdout(io.StringIO()):
                bench.score(args)
            scores = json.loads((path / "scores.json").read_text())
            self.assertEqual(scores["overall"]["manual_points_graded"], 2)
            self.assertEqual(scores["overall"]["manual_points"], 1)
            self.assertEqual(review.read_bytes(), review_before)
            predictions.write_text(predictions.read_text() + "\n")
            with self.assertRaisesRegex(ValueError, "hash has changed"):
                bench.score(args)


if __name__ == "__main__":
    unittest.main()
