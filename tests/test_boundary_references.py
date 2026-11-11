from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from verify_boundary_batch import active_ref_counts, pcm_luma, signed_distance


class BoundaryReferences(unittest.TestCase):
    def test_order_hint_math_matches_spec_masks_for_all_legal_widths(self):
        for bits in range(1, 9):
            m = 1 << (bits - 1)
            for a in range(2 * m):
                for b in range(2 * m):
                    diff = a - b
                    self.assertEqual(signed_distance(a, b, bits, 1), (diff & (m - 1)) - (diff & m))
        self.assertEqual(signed_distance(0, 0, 0, 0), 0)

    def test_illegal_pcm_inputs_and_unread_reference_field_rejected(self):
        with self.assertRaises(ValueError):
            pcm_luma(256, 8, 10)
        with self.assertRaises(ValueError):
            pcm_luma(1, 11, 10)
        with self.assertRaises(ValueError):
            active_ref_counts({'slice': 'P', 'entries': [1, 4], 'defaults_minus1': [0, 0],
                               'override': 1, 'active_minus1': [None, None]})


if __name__ == '__main__':
    unittest.main()
