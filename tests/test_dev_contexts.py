from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_dev_contexts import select_excerpt
from avllm_data import sha


class ContextExcerpts(unittest.TestCase):
    def test_exact_inclusive_slice(self):
        text = 'heading\nif enabled:\n    output = value\nnext clause\n'
        self.assertEqual(select_excerpt(text, {'parent_sha256': sha(text.encode()), 'start': 2, 'end': 3}),
                         'if enabled:\n    output = value')

    def test_stale_or_invalid_selection_is_rejected(self):
        text = 'first\nsecond'
        for start, end, digest in [(0, 1, sha(text.encode())), (2, 1, sha(text.encode())),
                                   (1, 3, sha(text.encode())), (True, 2, sha(text.encode())), (1, 2, 'stale')]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                select_excerpt(text, {'parent_sha256': digest, 'start': start, 'end': end})


if __name__ == '__main__':
    unittest.main()
