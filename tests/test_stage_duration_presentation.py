"""Duration formatting is pure UI, not a second MAIN/MIX timer."""
import unittest

from runtime.ui.components.stage_duration import (
    format_eta_compact,
    format_seconds_compact,
)


class StageDurationPresentationTests(unittest.TestCase):
    def test_existing_eta_labels(self):
        cases = (
            (None, "—"),
            ("", "—"),
            ("—", "—"),
            ("00:07", "7м"),
            ("01:03", "1ч 03м"),
            ("23:59", "23ч 59м"),
            ("00:00", "0м"),
            ("pending", "pending"),
            ("not:valid", "not:valid"),
            ("10:20:30", "10:20:30"),
        )
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(format_eta_compact(raw), expected)

    def test_existing_elapsed_duration_labels(self):
        cases = (
            (None, "—"),
            ("invalid", "—"),
            (-2, "0м"),
            (0, "0м"),
            (1, "1м"),
            (59, "1м"),
            (60, "1м"),
            (3660, "1ч 01м"),
            (7200, "2ч"),
            ("5400", "1ч 30м"),
        )
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(format_seconds_compact(raw), expected)
