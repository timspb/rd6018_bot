import tempfile
import time
import types
import unittest
from unittest.mock import patch

import bot as composition
from runtime import production_runtime as bot


class OperatorActionDebounceBoundaryTests(unittest.TestCase):
    def test_runtime_wrapper_retains_existing_dict_and_clock(self):
        from runtime.ui.commands.validation import allow_operator_action
        current = bot._action_debounce_until
        old = dict(current)
        try:
            current.clear()
            with patch.object(bot.time, "time", return_value=100.0):
                self.assertTrue(bot._is_action_allowed(7, "operator_pause_toggle", 1.5))
                self.assertFalse(bot._is_action_allowed(7, "operator_pause_toggle", 1.5))
            self.assertEqual(current, {"7:operator_pause_toggle": 101.5})
            self.assertTrue(allow_operator_action(current, 7, "operator_pause_toggle",
                                                  cooldown_sec=1.5, now_s=101.5))
        finally:
            current.clear()
            current.update(old)

    def test_command_and_user_have_independent_deadlines(self):
        from runtime.ui.commands.validation import allow_operator_action
        deadlines = {}
        self.assertTrue(allow_operator_action(deadlines, 7, "pause", now_s=50.0))
        self.assertTrue(allow_operator_action(deadlines, 8, "pause", now_s=50.0))
        self.assertTrue(allow_operator_action(deadlines, 7, "resume", now_s=50.0))
        self.assertFalse(allow_operator_action(deadlines, 7, "pause", now_s=50.5))
        self.assertTrue(allow_operator_action(deadlines, 7, "pause", now_s=51.2))


class FakePauseHass:
    def __init__(self, output="on"):
        self.live = {
            "switch": output,
            "battery_voltage": 14.6,
            "current": 0.4,
            "ah": 12.0,
            "temp_ext": 25.0,
            "input_voltage": 60.0,
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
        return True

    async def set_current(self, value):
        self.live["set_current"] = value
        return True


class _AsyncLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class FakePausePort:
    def __init__(self, hass):
        self.hass = hass
        self._guard_owner_lock = _AsyncLock()

    async def read_live(self):
        return await self.hass.get_all_live()

    async def request_verified_off(self):
        return await self.hass.turn_off()

    async def request_verified_on(self):
        return await self.hass.turn_on()

    async def program_voltage(self, value):
        return await self.hass.set_voltage(value)

    async def program_current(self, value):
        return await self.hass.set_current(value)


class OperatorPauseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.old_hass = bot.hass
        self.old_controller = bot.charge_controller
        self.old_pause = bot._operator_pause_state.started_at
        self.old_pause_file = bot.OPERATOR_PAUSE_FILE
        self.old_last_action = dict(bot._action_debounce_until)
        self.tempdir = tempfile.TemporaryDirectory()
        bot.OPERATOR_PAUSE_FILE = f"{self.tempdir.name}/operator_pause.json"
        bot._operator_pause_state.started_at = None
        bot._action_debounce_until.clear()

    def tearDown(self):
        bot.hass = self.old_hass
        bot.charge_controller = self.old_controller
        bot._operator_pause_state.started_at = self.old_pause
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
            shift_active_clocks=lambda _seconds: None,
        )

    async def test_pause_confirms_output_off_and_persists_session(self):
        bot.hass = FakePauseHass(output="on")
        bot.charge_controller = self._controller()
        bot._operator_pause_state.started_at = None

        port = FakePausePort(bot.hass)
        with patch.object(bot, "log_event"), patch.object(
            bot, "_runtime_execution_port", return_value=port
        ):
            result = await bot._operator_pause_toggle(self._call())

        self.assertIn("Пауза включена", result)
        self.assertEqual(bot.hass.turn_off_calls, 1)
        self.assertEqual(bot.hass.live["switch"], "off")
        self.assertTrue(bot._operator_pause_active())

    async def test_resume_uses_safe_enable_and_clears_pause(self):
        bot.hass = FakePauseHass(output="off")
        bot.charge_controller = self._controller()
        bot._operator_pause_state.started_at = time.time() - 10.0

        port = FakePausePort(bot.hass)
        with patch.object(bot, "log_event"), patch.object(
            bot, "_runtime_execution_port", return_value=port
        ):
            result = await bot._operator_pause_toggle(self._call())

        self.assertIn("Пауза снята", result)
        self.assertEqual(bot.hass.turn_on_calls, 1)
        self.assertEqual(bot.hass.live["switch"], "on")
        self.assertFalse(bot._operator_pause_active())


if __name__ == "__main__":
    unittest.main()
