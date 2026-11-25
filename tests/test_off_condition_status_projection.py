from __future__ import annotations

import unittest
from types import SimpleNamespace

from runtime.ui.components.off_condition_status import format_operator_off_conditions


def state(**overrides):
    values = dict(
        voltage_ge=None,
        voltage_le=None,
        current_le=None,
        current_ge=None,
        time_sec=None,
        start_time=0.0,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class OperatorOffConditionProjectionTests(unittest.TestCase):
    def test_empty_condition_is_hidden(self):
        self.assertEqual(format_operator_off_conditions(state(), now_s=100), "")

    def test_voltage_and_current_equal_thresholds_use_reached_wording(self):
        value = state(
            voltage_ge=14.2,
            voltage_le=14.205,
            current_le=0.3,
            current_ge=0.305,
        )
        self.assertEqual(
            format_operator_off_conditions(value, now_s=0),
            "⏹ ВЫКЛ ПО УСЛОВИЮ: при достижении V 14.20 В, "
            "при достижении I 0.30 А",
        )

    def test_threshold_difference_at_boundary_uses_separate_limits(self):
        value = state(voltage_ge=14.2, voltage_le=14.21)
        self.assertEqual(
            format_operator_off_conditions(value, now_s=0),
            "⏹ ВЫКЛ ПО УСЛОВИЮ: при V≥14.2 В, при V≤14.2 В",
        )

    def test_timer_formats_total_and_remaining_time_and_expires_at_zero(self):
        value = state(time_sec=2 * 3600 + 90, start_time=100)
        self.assertEqual(
            format_operator_off_conditions(value, now_s=100),
            "⏹ ВЫКЛ ПО УСЛОВИЮ: таймер 2:01 | осталось до выкл: 2:01",
        )
        self.assertEqual(
            format_operator_off_conditions(value, now_s=100 + value.time_sec),
            "⏹ ВЫКЛ ПО УСЛОВИЮ: таймер истёк",
        )


if __name__ == "__main__":
    unittest.main()
