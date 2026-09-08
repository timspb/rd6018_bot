import tempfile
import time
import types
import unittest
from unittest.mock import patch

import bot


class FakePauseHass:
    def __init__(self, output="on"):
        self.live = {
            "switch": output,
            "battery_voltage": 14.6,
            "current": 0.4,
            "ah": 12.0,
            "temp_ext": 25.0,
            "input_voltage": 60.0,
            "ovp_triggered": "off",
            "ocp_triggered": "off",
        }
        self.turn_off_calls = 0
        self.turn_on_calls = 0

    async def get_all_live(self):
        return dict(self.live)

    async def turn_off(self, _entity_id=None):
        self.turn_off_calls += 1
        self.live["switch"] = "off"
        return True

    async def turn_on(self, _entity_id=None):
        self.turn_on_calls += 1
        self.live["switch"] = "on"
        return True

    async def set_voltage(self, value):
        self.live["set_voltage"] = value

    async def set_current(self, value):
        self.live["set_current"] = value

    async def set_ovp(self, value):
        self.live["ovp"] = value

    async def set_ocp(self, value):
        self.live["ocp"] = value


class OperatorPauseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.old_hass = bot.hass
        self.old_controller = bot.charge_controller
        self.old_pause = bot.operator_pause_started_at
        self.old_pause_file = bot.OPERATOR_PAUSE_FILE
        self.old_last_action = dict(bot._action_debounce_until)
        self.tempdir = tempfile.TemporaryDirectory()
        bot.OPERATOR_PAUSE_FILE = f"{self.tempdir.name}/operator_pause.json"
        bot._action_debounce_until.clear()

    def tearDown(self):
        bot.hass = self.old_hass
        bot.charge_controller = self.old_controller
        bot.operator_pause_started_at = self.old_pause
        bot.OPERATOR_PAUSE_FILE = self.old_pause_file
        bot._action_debounce_until.clear()
        bot._action_debounce_until.update(self.old_last_action)
        self.tempdir.cleanup()

    @staticmethod
    def _call():
        return types.SimpleNamespace(
            from_user=types.SimpleNamespace(id=700001),
            message=types.SimpleNamespace(chat=types.SimpleNamespace(id=700002)),
        )

    def _controller(self):
        return types.SimpleNamespace(
            is_active=True,
            current_stage="CV",
            STAGE_SAFE_WAIT="SAFE_WAIT",
            _save_session=lambda *_args: None,
            _get_target_v_i=lambda _temp: (14.7, 0.3),
        )

    async def test_pause_confirms_output_off_and_persists_session(self):
        bot.hass = FakePauseHass(output="on")
        bot.charge_controller = self._controller()
        bot.operator_pause_started_at = None

        with patch.object(bot, "log_event"):
            result = await bot._operator_pause_toggle(self._call())

        self.assertIn("Пауза включена", result)
        self.assertEqual(bot.hass.turn_off_calls, 1)
        self.assertEqual(bot.hass.live["switch"], "off")
        self.assertTrue(bot._operator_pause_active())

    async def test_resume_uses_safe_enable_and_clears_pause(self):
        bot.hass = FakePauseHass(output="off")
        bot.charge_controller = self._controller()
        bot.operator_pause_started_at = time.time() - 10.0

        with patch.object(bot, "log_event"), patch.object(
            bot, "_apply_phase_protection", return_value=None
        ):
            result = await bot._operator_pause_toggle(self._call())

        self.assertIn("Пауза снята", result)
        self.assertEqual(bot.hass.turn_on_calls, 1)
        self.assertEqual(bot.hass.live["switch"], "on")
        self.assertFalse(bot._operator_pause_active())


if __name__ == "__main__":
    unittest.main()
