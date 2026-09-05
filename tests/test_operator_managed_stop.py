import types
import unittest

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import operator_hmi as hmi
from operator_managed_stop import _replace_legacy_power_toggle, _stop_exact_session


class FakeManual:
    def __init__(self, *, confirmed=True):
        self.is_active = True
        self.started_at = 123.0
        self.confirmed = confirmed
        self.stop_calls = []
        self.retired = 0

    async def stop(self, reason):
        self.stop_calls.append(reason)
        if self.confirmed:
            self.is_active = False
        return self.confirmed

    async def _retire_runner(self):
        self.retired += 1


class OperatorManagedStopTests(unittest.IsolatedAsyncioTestCase):
    def _state(self, authority):
        return hmi.OperatorHmiState(
            process_state=hmi.HmiProcessState.RUNNING,
            authority=authority,
            title="",
            output_on=True,
            regulator="CV",
            battery_label="",
            battery_voltage_v=14.8,
            current_a=1.0,
            power_w=14.8,
            battery_temp_c=25.0,
            psu_temp_c=35.0,
            target_voltage_v=14.8,
            current_limit_a=5.0,
            progress="",
            safety="",
        )

    def test_managed_keyboard_uses_stop_only_callback_not_legacy_power_toggle(self):
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🛑 Остановить заряд", callback_data="power_toggle")],
                [InlineKeyboardButton(text="ℹ Подробнее", callback_data="operator_details")],
            ]
        )
        result = _replace_legacy_power_toggle(markup, self._state(hmi.HmiAuthority.AUTO))
        callbacks = [b.callback_data for row in result.inline_keyboard for b in row]
        self.assertIn("operator_managed_stop", callbacks)
        self.assertNotIn("power_toggle", callbacks)

    def test_nonmanaged_keyboard_does_not_rewrite_unrelated_legacy_callback(self):
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="x", callback_data="power_toggle")]]
        )
        result = _replace_legacy_power_toggle(markup, self._state(hmi.HmiAuthority.NONE))
        self.assertEqual(result.inline_keyboard[0][0].callback_data, "power_toggle")

    async def test_exact_auto_stop_uses_existing_hard_stop_and_never_toggle_path(self):
        controller = types.SimpleNamespace(
            is_active=True,
            recovery_trace_context={"session_id": "auto-1"},
            total_start_time=1.0,
        )
        calls = []

        async def hard_stop():
            calls.append("hard_stop")
            controller.is_active = False

        app = types.SimpleNamespace(
            charge_controller=controller,
            manual_session_manager=types.SimpleNamespace(is_active=False),
            _hard_stop_charge=hard_stop,
            _clear_manual_off=lambda: calls.append("clear_off"),
        )
        ok, detail = await _stop_exact_session(app, "auto:auto-1")
        self.assertTrue(ok)
        self.assertIn("Output OFF", detail)
        self.assertEqual(calls, ["hard_stop", "clear_off"])

    async def test_stale_auto_confirmation_is_non_actuating(self):
        controller = types.SimpleNamespace(
            is_active=True,
            recovery_trace_context={"session_id": "replacement"},
            total_start_time=2.0,
        )
        calls = []

        async def hard_stop():
            calls.append("hard_stop")

        app = types.SimpleNamespace(
            charge_controller=controller,
            manual_session_manager=types.SimpleNamespace(is_active=False),
            _hard_stop_charge=hard_stop,
        )
        ok, detail = await _stop_exact_session(app, "auto:old")
        self.assertFalse(ok)
        self.assertIn("изменилась", detail)
        self.assertEqual(calls, [])

    async def test_manual_stop_retires_manual_owner_not_auto_controller(self):
        manual = FakeManual(confirmed=True)
        auto_calls = []
        app = types.SimpleNamespace(
            charge_controller=types.SimpleNamespace(is_active=False),
            manual_session_manager=manual,
            _hard_stop_charge=lambda: auto_calls.append("wrong"),
            _clear_manual_off=lambda: None,
        )
        ok, detail = await _stop_exact_session(app, "manual:123.000000")
        self.assertTrue(ok)
        self.assertIn("Output OFF", detail)
        self.assertEqual(manual.stop_calls, ["operator_stop"])
        self.assertEqual(manual.retired, 1)
        self.assertEqual(auto_calls, [])

    async def test_unconfirmed_manual_off_keeps_containment_and_does_not_retire_runner(self):
        manual = FakeManual(confirmed=False)
        app = types.SimpleNamespace(
            charge_controller=types.SimpleNamespace(is_active=False),
            manual_session_manager=manual,
        )
        ok, detail = await _stop_exact_session(app, "manual:123.000000")
        self.assertFalse(ok)
        self.assertIn("не подтверждён", detail)
        self.assertTrue(manual.is_active)
        self.assertEqual(manual.retired, 0)


if __name__ == "__main__":
    unittest.main()
