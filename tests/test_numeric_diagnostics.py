from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from diagnose_numeric import content_result
from dev_benchmark import numeric_result


class NumericDiagnostics(unittest.TestCase):
    def test_multiline_json_content_is_separate_from_strict_format(self):
        text = '{\n  "n": 23\n}'
        self.assertEqual(numeric_result(text, {'n': 23}), 'unparseable')
        self.assertEqual(content_result(text, {'n': 23}), 'correct')
        self.assertEqual(content_result('说明\n```json\n' + text + '\n```', {'n': 23}), 'correct')
        self.assertEqual(content_result(text, {'n': 24}), 'incorrect')

    def test_no_arithmetic_coercion_or_ambiguous_json(self):
        for text in ('{"n": 26-8+5}', '{"n": true}', '{"n": "23"}', '{"n":23,"n":24}',
                     '{"n":23,"extra":0}', '结果是23', '{"n":23}\n继续解释'):
            with self.subTest(text=text):
                self.assertEqual(content_result(text, {'n': 23}), 'unparseable')


if __name__ == '__main__':
    unittest.main()
