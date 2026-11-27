import asyncio
import pathlib
import types
import unittest
from unittest.mock import AsyncMock

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import ENTITY_MAP
from rd6018_telemetry import canonicalize_live
from operator_mix_eligibility import (
    POTENTIAL_MIX_MIN_SETPOINT_V,
    filter_non_mix_actions,
    potential_mix_setpoint,
    install_mix_action_eligibility,
)
from application.operator_actions import OperatorAction, OperatorActionSpec, OperatorActionsView
from runtime.ui.components.hmi_state import HmiAuthority, HmiProcessState, OperatorHmiState
import operator_hmi


class LiveOutputReadbackV2Tests(unittest.TestCase):
    def test_deployed_output_state_entity_id_is_exact(self):
        self.assertEqual(
            ENTITY_MAP["output_state_code_v2"],
            "sensor.rd6018_rd_6018_output_state_code_v2",
        )

    def test_read_only_output_code_owns_canonical_value_and_freshness(self):
        live = {
            "switch": "on",
            "output_state_code_v2": 0,
            "_meta": {
                "switch": {"status": "ok", "last_reported": "old"},
                "output_state_code_v2": {
                    "status": "ok",
                    "last_reported": "fresh",
                    "last_updated": "fresh",
                },
            },
        }

        promoted = canonicalize_live(live)

        self.assertEqual(promoted["switch"], "off")
        self.assertEqual(promoted["_meta"]["switch"]["last_reported"], "fresh")
        self.assertEqual(
            promoted["_meta"]["switch"]["source_key"],
            "output_state_code_v2",
        )

    def test_invalid_output_code_never_overrides_public_switch(self):
        live = {"switch": "on", "output_state_code_v2": 2, "_meta": {}}
        promoted = canonicalize_live(live)
        self.assertEqual(promoted["switch"], "on")

    def test_hass_canonicalization_owns_output_promotion_before_safety_capture(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        hass_source = (root / "hass_api.py").read_text(encoding="utf-8")
        bot_source = (root / "bot.py").read_text(encoding="utf-8")

        self.assertIn("canonicalize_live(", hass_source)
        self.assertNotIn("install_output_state_readback", bot_source)
        self.assertNotIn("live_output_readback_v2", bot_source)


class MixActionEligibilityTests(unittest.TestCase):
    def test_low_voltage_hands_off_program_is_not_potential_mix(self):
        self.assertFalse(potential_mix_setpoint(13.60))
        self.assertFalse(potential_mix_setpoint(POTENTIAL_MIX_MIN_SETPOINT_V))
        self.assertTrue(potential_mix_setpoint(POTENTIAL_MIX_MIN_SETPOINT_V + 0.01))

    def test_filter_removes_only_mix_entry_actions(self):
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="observer", callback_data="rd_live_mix")],
                [InlineKeyboardButton(text="managed", callback_data="rd_managed_mix")],
                [InlineKeyboardButton(text="Pb", callback_data="rd_managed_adopt")],
                [InlineKeyboardButton(text="OFF", callback_data="rd_hands_off_output_off")],
            ]
        )

        filtered = filter_non_mix_actions(markup)
        callbacks = [
            button.callback_data
            for row in filtered.inline_keyboard
            for button in row
            if button.callback_data
        ]
        self.assertNotIn("rd_live_mix", callbacks)
        self.assertNotIn("rd_managed_mix", callbacks)
        self.assertIn("rd_managed_adopt", callbacks)
        self.assertIn("rd_hands_off_output_off", callbacks)

    @staticmethod
    def _state(target_voltage, *, output_on=True):
        return OperatorHmiState(
            process_state=HmiProcessState.HANDS_OFF,
            authority=HmiAuthority.EXTERNAL,
            title="HANDS_OFF", output_on=output_on, regulator="", battery_label="",
            battery_voltage_v=None, current_a=None, power_w=None, battery_temp_c=None,
            psu_temp_c=None, target_voltage_v=target_voltage, current_limit_a=None,
            progress="", safety="",
        )

    @staticmethod
    def _callbacks(markup):
        return [button.callback_data for row in markup.inline_keyboard for button in row]

    def test_real_builder_projects_mix_per_state_and_actions_argument_bypasses_mix_filter(self):
        class Middleware:
            def __init__(self):
                self.handlers = []

            def register(self, handler):
                self.handlers.append(handler)

        def app():
            middleware = Middleware()
            return types.SimpleNamespace(
                router=types.SimpleNamespace(
                    callback_query=types.SimpleNamespace(outer_middleware=middleware)
                ),
                rd_control_mode_manager=types.SimpleNamespace(
                    guard=types.SimpleNamespace(_raw_live=AsyncMock(return_value={"set_voltage": 13.6}))
                ),
            )

        first, second = app(), app()
        # D062 entry is an app-scoped action. Install a fake current owner
        # explicitly rather than relying on global import/installer leakage.
        first.rd_managed_mix_adoption = types.SimpleNamespace(active=False, off_pending=False)
        second.rd_managed_mix_adoption = types.SimpleNamespace(active=False, off_pending=False)
        install_mix_action_eligibility(first)
        install_mix_action_eligibility(second)
        low = self._state(13.6)
        high = self._state(POTENTIAL_MIX_MIN_SETPOINT_V + 0.1)

        low_callbacks = self._callbacks(operator_hmi.build_operator_keyboard(first, low))
        high_callbacks = self._callbacks(operator_hmi.build_operator_keyboard(second, high))
        self.assertNotIn("rd_live_mix", low_callbacks)
        self.assertIn("rd_live_mix", high_callbacks)
        self.assertEqual(low_callbacks, ["rd_hands_off_output_off", "operator_refresh"])
        # The composed D062 owner adds a second allowed Mix entry at high
        # voltage. Both must disappear when setpoints cannot be Mix.
        self.assertIn("rd_managed_mix", high_callbacks)
        self.assertNotIn("rd_managed_mix", low_callbacks)
        self.assertEqual(high_callbacks, [
            "rd_live_mix", "rd_managed_mix",
            "rd_hands_off_output_off", "operator_refresh",
        ])
        self.assertIn("rd_hands_off_output_off", low_callbacks)

        output_off = self._state(13.6, output_on=False)
        off_callbacks = self._callbacks(operator_hmi.build_operator_keyboard(first, output_off))
        self.assertNotIn("rd_live_mix", off_callbacks)
        self.assertNotIn("rd_hands_off_output_off", off_callbacks)

        output_unknown = self._state(13.6)
        object.__setattr__(output_unknown, "_output_state_known", False)
        unknown_callbacks = self._callbacks(operator_hmi.build_operator_keyboard(first, output_unknown))
        self.assertNotIn("rd_live_mix", unknown_callbacks)
        self.assertIn("rd_hands_off_output_off", unknown_callbacks)

        # The established explicit-actions branch skips the presentation
        # eligibility projection, while still passing through final output truth.
        provided = operator_hmi.build_operator_keyboard(
            first,
            low,
            actions=OperatorActionsView(available_actions=(OperatorActionSpec(OperatorAction.ADOPT_MIX),)),
        )
        self.assertIn("rd_live_mix", self._callbacks(provided))

        import inspect

        installer_source = inspect.getsource(install_mix_action_eligibility)
        self.assertNotIn("operator_hmi.build_operator_keyboard =", installer_source)

    def test_mix_installer_is_idempotent_and_keeps_one_fresh_live_middleware(self):
        class Middleware:
            def __init__(self):
                self.handlers = []

            def register(self, handler):
                self.handlers.append(handler)

        class Guard:
            def __init__(self, result=None, error=None):
                self.result, self.error, self.reads = result, error, 0

            async def _raw_live(self):
                self.reads += 1
                if self.error:
                    raise self.error
                return self.result

        middleware = Middleware()
        guard = Guard({"set_voltage": 13.6})
        app = types.SimpleNamespace(
            router=types.SimpleNamespace(callback_query=types.SimpleNamespace(outer_middleware=middleware)),
            rd_control_mode_manager=types.SimpleNamespace(guard=guard),
        )
        install_mix_action_eligibility(app)
        registered = middleware.handlers[0]
        install_mix_action_eligibility(app)
        self.assertEqual(middleware.handlers, [registered])
        self.assertFalse(hasattr(operator_hmi, "_mix_action_eligibility_installed"))

        handler = AsyncMock(return_value="accepted")

        class Event:
            def __init__(self, data):
                self.data, self.answers = data, []

            async def answer(self, *args, **kwargs):
                self.answers.append((args, kwargs))

        async def invoke(event):
            return await registered(handler, event, {})

        low_event = Event("rd_live_mix")
        self.assertIsNone(asyncio.run(invoke(low_event)))
        self.assertEqual(guard.reads, 1)
        handler.assert_not_awaited()
        self.assertTrue(low_event.answers)

        guard.result = {"set_voltage": POTENTIAL_MIX_MIN_SETPOINT_V + 0.1}
        allowed_event = Event("rd_managed_mix")
        self.assertEqual(asyncio.run(invoke(allowed_event)), "accepted")
        self.assertEqual(guard.reads, 2)
        handler.assert_awaited_once_with(allowed_event, {})

        handler.reset_mock()
        guard.error = RuntimeError("live read failed")
        failed_event = Event("rd_live_mix")
        self.assertIsNone(asyncio.run(invoke(failed_event)))
        self.assertEqual(guard.reads, 3)
        handler.assert_not_awaited()
        self.assertTrue(failed_event.answers)


class ESPHomeSourceHeartbeatContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = pathlib.Path("esphome/rd6018.yaml").read_text(encoding="utf-8")
        cls.telemetry = pathlib.Path(
            "esphome/packages/rd6018_telemetry_v2.yaml"
        ).read_text(encoding="utf-8")

    @staticmethod
    def _block(text: str, name: str) -> str:
        return text.split(f'name: "{name}"', 1)[1].split("- platform:", 1)[0]

    def test_stable_critical_numeric_sources_force_ha_reports(self):
        for name in ("Output voltage", "Output current", "Battery voltage"):
            with self.subTest(name=name):
                self.assertIn("force_update: true", self._block(self.node, name))

        for name in (
            "Temperature Internal V2",
            "Temperature External V2",
            "Protection Status Code",
            "Regulation Mode Code",
        ):
            with self.subTest(name=name):
                self.assertIn("force_update: true", self._block(self.telemetry, name))

    def test_output_has_force_updated_read_only_register_18_source(self):
        block = self._block(self.telemetry, "Output State Code V2")
        self.assertIn("address: 18", block)
        self.assertIn("value_type: U_WORD", block)
        self.assertIn("force_update: true", block)


if __name__ == "__main__":
    unittest.main()
