from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from runtime.ui.telegram.text_input_parser import (
    parse_off_command,
    parse_three_values,
    parse_two_numbers,
)


MAX_CURRENT = 12.0


class TelegramTextInputParserTests(unittest.TestCase):
    def test_off_defaults_explicit_conditions_and_timer(self):
        clock = Mock(return_value=123.5)
        self.assertEqual(
            parse_off_command("off 16,4 1.23 2:03", max_stage_current=MAX_CURRENT, clock=clock),
            {
                "voltage_ge": 16.4,
                "voltage_le": None,
                "current_le": 1.23,
                "current_ge": None,
                "time_sec": 7380,
                "start_time": 123.5,
                "parts": ["16.4 В (V≥)", "1.23 А (I≤)", "таймер 2:03"],
            },
        )
        self.assertEqual(
            parse_off_command("OFF V≥13.2 I≥2", max_stage_current=MAX_CURRENT, clock=clock)["parts"],
            ["V≥13.2 В", "I≥2.00 А"],
        )
        self.assertEqual(
            parse_off_command("off 12", max_stage_current=MAX_CURRENT, clock=clock)["voltage_ge"],
            12.0,
        )
        self.assertEqual(
            parse_off_command("off 0.1", max_stage_current=MAX_CURRENT, clock=clock)["current_le"],
            0.1,
        )

    def test_off_invalid_and_no_match_do_not_read_clock(self):
        clock = Mock(return_value=5.0)
        for value in ("off", "off invalid", "OFF 99", "16.4", "off 0"):
            with self.subTest(value=value):
                self.assertIsNone(
                    parse_off_command(value, max_stage_current=MAX_CURRENT, clock=clock)
                )
        clock.assert_not_called()

    def test_three_value_timer_and_latin_cyrillic_units(self):
        self.assertEqual(parse_three_values("16,5 1,4 2:35", max_stage_current=MAX_CURRENT),
                         {"v": 16.5, "i": 1.4, "time_sec": 9300})
        self.assertEqual(parse_three_values("16.5 1.4 2.35A", max_stage_current=MAX_CURRENT),
                         {"v": 16.5, "i": 1.4, "off_current": 2.35})
        self.assertEqual(parse_three_values("16.5 1.4 2.35А", max_stage_current=MAX_CURRENT),
                         {"v": 16.5, "i": 1.4, "off_current": 2.35})
        self.assertEqual(parse_three_values("16.5 1.4 15V", max_stage_current=MAX_CURRENT),
                         {"v": 16.5, "i": 1.4, "off_voltage": 15.0})
        self.assertEqual(parse_three_values("16.5 1.4 15В", max_stage_current=MAX_CURRENT),
                         {"v": 16.5, "i": 1.4, "off_voltage": 15.0})
        self.assertIsNone(parse_three_values("16.5 1.4 0:00", max_stage_current=MAX_CURRENT))
        self.assertIsNone(parse_three_values("16.5 1.4 13A", max_stage_current=MAX_CURRENT))
        self.assertIsNone(parse_three_values("16.5 1.4", max_stage_current=MAX_CURRENT))

    def test_two_number_grammar_and_invalid_input(self):
        self.assertEqual(parse_two_numbers("16,50 1,4"), (16.5, 1.4))
        self.assertIsNone(parse_two_numbers("16.5 one"))
        self.assertIsNone(parse_two_numbers("16.5 1.4 extra"))

    def test_production_runtime_wrappers_call_extracted_owner(self):
        from runtime import production_runtime

        with patch.object(production_runtime, "_parse_off_command_impl", return_value={"start_time": 7}) as off:
            self.assertEqual(production_runtime._parse_off_command("off 2"), {"start_time": 7})
            off.assert_called_once_with(
                "off 2", max_stage_current=production_runtime.MAX_STAGE_CURRENT,
                clock=production_runtime.time.time,
            )
        with patch.object(production_runtime, "_parse_three_values_impl", return_value={"v": 1}) as three:
            self.assertEqual(production_runtime._parse_three_values("1 2 3A"), {"v": 1})
            three.assert_called_once_with("1 2 3A", max_stage_current=production_runtime.MAX_STAGE_CURRENT)
        with patch.object(production_runtime, "_parse_two_numbers_impl", return_value=(1, 2)) as two:
            self.assertEqual(production_runtime._parse_two_numbers("1 2"), (1, 2))
            two.assert_called_once_with("1 2")


if __name__ == "__main__":
    unittest.main()
