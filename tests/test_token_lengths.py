from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_token_lengths import message_lengths


class TokenLengths(unittest.TestCase):
    def test_dictionary_default_cannot_hide_over_limit_sample(self):
        def chat(messages, **options):
            tokens = list(range(2049))
            return {"input_ids": tokens, "attention_mask": [1] * len(tokens)} if options.get("return_dict", True) else tokens
        tokenizer = SimpleNamespace(apply_chat_template=chat)
        lengths = message_lengths(tokenizer, [{"messages": [{"role": "user", "content": "fixture"}]}])
        self.assertEqual(lengths, [2049])
        self.assertGreater(lengths[0], 2048)

    def test_unexpected_token_shapes_are_rejected(self):
        for result in ({"input_ids": [1, 2]}, [[1, 2]], [], ["input_ids", "attention_mask"]):
            with self.subTest(result=result), self.assertRaises(ValueError):
                message_lengths(SimpleNamespace(apply_chat_template=lambda *a, **k: result), [{"messages": []}])


if __name__ == "__main__":
    unittest.main()
