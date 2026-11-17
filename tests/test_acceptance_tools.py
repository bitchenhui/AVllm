from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from avllm_data import sha
from blind_review import aggregate
from local_calculator import calculate, request
from retrieve_acceptance_context import search, terms
from collections import Counter


class AcceptanceTools(unittest.TestCase):
    def test_calc_integer_semantics_and_bounds(self):
        self.assertEqual(calculate("(-230 >> 4) + 64"), 49)
        self.assertEqual(calculate("(8 - 11) % 256"), 253)
        for invalid in ["x+2", "5/2", "1<<64", "1<<-1", "1//0", "2**8", "99999999*999999999999"]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                calculate(invalid)
        self.assertEqual(request("推导\nCALC: 2+3\n"), "2+3")
        self.assertIsNone(request("CALC: 2+3\n最终答案"))

    def test_retrieval_prefers_specific_match_and_skips_overlap(self):
        def chunk(page, start, end, txt):
            words = Counter(terms(txt))
            return page, start, end, txt, words, sum(words.values())
        chunks = [chunk(1, 1, 2, "header setup"), chunk(2, 1, 25, "preCtxState initialization"),
                  chunk(2, 15, 40, "preCtxState context"), chunk(3, 1, 30, "context state")]
        got = search(chunks, "preCtxState")
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0][0], 2)

    def test_blind_review_requires_hash_and_complete_coverage(self):
        queue = [{"id": "q", "answers": {"A": "first", "B": "second"}, "rubric": [{"id": "p1"}]}]
        identities = [{"id": "q", "label": label, "run": name, "answer_sha256": sha(text.encode())}
                      for label, name, text in [("A", "x", "first"), ("B", "y", "second")]]
        ratings = [{"id": "q", "label": label, "points": {"p1": value}, "note": "criterion"}
                   for label, value in [("A", 1), ("B", 0)]]
        self.assertEqual(aggregate(queue, identities, ratings)["totals"]["x"]["points"], 1)
        with self.assertRaises(ValueError):
            aggregate(queue, identities, ratings[:1])
        with self.assertRaises(ValueError):
            aggregate(queue, identities[:1], ratings[:1])
        with self.assertRaises(ValueError):
            aggregate([dict(queue[0], answers={"A": "changed", "B": "second"})], identities, ratings)


if __name__ == "__main__":
    unittest.main()
