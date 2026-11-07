"""Readable graph ranges for measured U/I at constant and changing loads."""
from __future__ import annotations

import unittest

import graphing


class GraphAutoscaleTests(unittest.TestCase):
    def test_stable_low_current_not_flattened_at_zero(self):
        low, high = graphing._visible_axis_limits([0.23] * 20, minimum_span=0.10)
        self.assertGreater(low, 0.0)
        self.assertLess(low, 0.23)
        self.assertGreater(high, 0.23)
        self.assertLess(high, 0.5)

    def test_stable_voltage_not_flattened_between_zero_and_twenty(self):
        low, high = graphing._visible_axis_limits([14.76] * 20, minimum_span=0.30)
        self.assertGreater(low, 13.0)
        self.assertLess(low, 14.76)
        self.assertGreater(high, 14.76)
        self.assertLess(high, 16.0)

    def test_off_current_includes_zero(self):
        self.assertEqual(graphing._visible_axis_limits([0.0, 0.0], minimum_span=0.10),
                         (0.0, 0.10))

    def test_startup_range_does_not_clip_actual_peak(self):
        low, high = graphing._visible_axis_limits([0.0, 0.23, 1.7, 7.9], minimum_span=0.10)
        self.assertEqual(low, 0.0)
        self.assertGreater(high, 7.9)

    def test_three_traces_render_readable_low_current_axis(self):
        chart = graphing.generate_chart(
            [f"2026-11-07T12:{m:02d}:00Z" for m in range(12)],
            [14.76] * 12,
            [0.23] * 12,
            [26.0] * 12,
        )
        self.assertIsNotNone(chart)
        self.assertGreater(len(chart.getvalue()), 100)
        axes = graphing._FIGURE.axes
        self.assertEqual(len(axes), 3)
        self.assertGreater(axes[1].get_ylim()[0], 0)
        self.assertLess(axes[1].get_ylim()[1], 0.5)
        self.assertGreater(axes[0].get_ylim()[0], 13)

    def test_two_trace_chart_uses_same_scaling(self):
        chart = graphing.generate_chart(
            [f"2026-11-07T12:{m:02d}:00Z" for m in range(8)],
            [14.76] * 8,
            [0.23] * 8,
        )
        self.assertIsNotNone(chart)
        axes = graphing._FIGURE.axes
        self.assertEqual(len(axes), 2)
        self.assertGreater(axes[1].get_ylim()[0], 0)
        self.assertLess(axes[1].get_ylim()[1], 0.5)


if __name__ == "__main__":
    unittest.main()
