import types
import unittest

from aiogram.enums import ParseMode

from battery_fault_engine import DiagnosticAuthority
from pb_domain import BatteryCondition
from safe_output import EnableResult, SafetyViolation
from v2_mix_mode import (
    PendingMixStart,
    build_mix_only_preview,
    start_mix_transactional,
)


class FakeMessage:
    def __init__(self):
        self.chat = types.SimpleNamespace(id=123)
        self.from_user = types.SimpleNamespace(id=7)
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


class FakeController:
    STAGE_MIX = "Mix Mode"

    def __init__(self):
        self.is_active = False
        self.current_stage = "Idle"
        self.full_start_called = False
        self.stopped = False
        self.context = None
        self.stage_start_time = 0.0
        self._v2_trace_started_at = 0.0
        self._v2_battery_id = None
        self._start_ah = 0.0
        self._stage_start_ah = 0.0
        self._stage_start_voltage = 0.0
        self._stage_start_current = 0.0
        self._stage_start_temp = 0.0
        self.blank_at = None
        self.battery_fault_assessment = types.SimpleNamespace(
            authority=DiagnosticAuthority.ALLOW,
            authority_reasons=(),
        )

    def start(self, *args, **kwargs):
        self.full_start_called = True
        raise AssertionError("Mix-only must not call full start()")

    def configure_recovery_context(self, **kwargs):
        self.context = kwargs
        self._v2_battery_id = kwargs["battery_id"]

    async def _refresh_stored_diagnostics(self):
        return None

    def _init_session(self, profile, capacity, start_stage):
        self.profile = profile
        self.capacity = capacity
        self.current_stage = start_stage
        self.is_active = True
        self.stage_start_time = 1000.0

    def _reset_delta_and_blanking(self, now):
        self.blank_at = now

    def _begin_trace_identity(self):
        self._v2_trace_started_at = 1000.0

    def _initialize_shadow_session(self, *, started_at):
        self.shadow_started_at = started_at

    def _mix_target(self, temp):
        if self.profile == "AGM":
            return 16.3, min(12.0, self.capacity * 0.03)
        return 16.5, min(12.0, self.capacity * 0.03)

    def stop(self, clear_session=True):
        self.stopped = True
        self.is_active = False
        self.current_stage = "Idle"


class FakeHass:
    def __init__(self, result):
        self.result = result
        self.enable_kwargs = None
        self.turn_off_calls = 0
        self.turn_off_result = True
        self.live = {
            "battery_voltage": 12.6,
            "voltage": 0.0,
            "current": 0.0,
            "temp_ext": 25.0,
            "temp_int": 32.0,
            "input_voltage": 64.0,
            "switch": "off",
            "ovp_triggered": "off",
            "ocp_triggered": "off",
            "set_voltage": 16.5,
            "set_current": 2.1,
            "ovp": 16.6,
            "ocp": 2.2,
            "ah": 4.0,
        }

    async def get_all_live(self):
        return dict(self.live)

    async def safe_enable_output(self, **kwargs):
        self.enable_kwargs = kwargs
        return self.result

    async def turn_off(self, entity_id=None):
        self.turn_off_calls += 1
        if self.turn_off_result:
            self.live["switch"] = "off"
        return self.turn_off_result


class FakeApp:
    ParseMode = ParseMode
    OVP_OFFSET = 0.1
    OCP_OFFSET = 0.1
    ENTITY_MAP = {"switch": "switch.rd6018"}

    def __init__(self, result):
        self.charge_controller = FakeController()
        self.hass = FakeHass(result)
        self.user_dashboard = {}
        self.last_checkpoint_time = 0.0
        self.last_chat_id = None
        self.last_user_id = None
        self.time = types.SimpleNamespace(time=lambda: 1000.0)
        self.events = []

    @staticmethod
    def _safe_float(value, default=0.0):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _cap_current(value):
        return min(12.0, max(0.1, float(value)))

    def log_event(self, *args):
        self.events.append(args)

    async def send_dashboard(self, *args, **kwargs):
        return 1


PENDING = PendingMixStart(
    profile="EFB",
    capacity_ah=70.0,
    battery_id="efb-70",
    condition=BatteryCondition.UNKNOWN,
)


class V2MixOnlyTests(unittest.IsolatedAsyncioTestCase):
    def test_preview_is_explicitly_mix_only(self):
        text = build_mix_only_preview(PENDING)
        self.assertIn("Старт сразу с Mix", text)
        self.assertIn("PREP, Main", text)
        self.assertIn("24 ч активного Mix", text)
        self.assertIn("Imin →", text)
        self.assertIn("Vmax →", text)
        self.assertIn("MIX_TIMEOUT", text)
        self.assertIn("Output OFF", text)
        self.assertIn("Нормальное завершение по Delta", text)
        self.assertIn("Storage", text)

    async def test_direct_mix_start_never_enters_full_auto_start(self):
        app = FakeApp(EnableResult(enabled=True))
        message = FakeMessage()

        ok = await start_mix_transactional(app, message, PENDING)

        self.assertTrue(ok)
        self.assertFalse(app.charge_controller.full_start_called)
        self.assertEqual(app.charge_controller.current_stage, app.charge_controller.STAGE_MIX)
        self.assertAlmostEqual(app.hass.enable_kwargs["voltage_v"], 16.5)
        self.assertAlmostEqual(app.hass.enable_kwargs["current_a"], 2.1)
        self.assertAlmostEqual(app.hass.enable_kwargs["recipe_voltage_ceiling_v"], 16.5)
        self.assertEqual(app.charge_controller.context["intent"].value, "normal")
        self.assertIn("MIX_ONLY", app.events[-1][-1])
        self.assertIn("Auto Mix запущен", message.answers[-1][0])

    async def test_low_battery_is_rejected_without_hidden_prep(self):
        app = FakeApp(EnableResult(enabled=True))
        app.hass.live["battery_voltage"] = 11.99
        message = FakeMessage()

        ok = await start_mix_transactional(app, message, PENDING)

        self.assertFalse(ok)
        self.assertFalse(app.charge_controller.is_active)
        self.assertFalse(app.charge_controller.full_start_called)
        self.assertIsNone(app.hass.enable_kwargs)
        self.assertIn("11.99", message.answers[-1][0])
        self.assertIn("сначала нужен обычный заряд/PREP", message.answers[-1][0])

    async def test_confirmed_cell_fault_blocks_mix_before_session_or_hardware(self):
        app = FakeApp(EnableResult(enabled=True))
        app.charge_controller.battery_fault_assessment = types.SimpleNamespace(
            authority=DiagnosticAuthority.BLOCK_AUTOMATIC_HV,
            authority_reasons=("external_failed_cell_confirmed",),
        )
        message = FakeMessage()

        ok = await start_mix_transactional(app, message, PENDING)

        self.assertFalse(ok)
        self.assertFalse(app.charge_controller.is_active)
        self.assertIsNone(app.hass.enable_kwargs)
        self.assertIn("заблокирован диагностикой", message.answers[-1][0])

    async def test_failed_safe_enable_rolls_back_only_after_confirmed_off(self):
        app = FakeApp(
            EnableResult(
                enabled=False,
                violations=frozenset({SafetyViolation.READBACK_MISMATCH}),
                detail="setpoint readback mismatch",
            )
        )
        message = FakeMessage()

        ok = await start_mix_transactional(app, message, PENDING)

        self.assertFalse(ok)
        self.assertTrue(app.charge_controller.stopped)
        self.assertEqual(app.hass.turn_off_calls, 1)
        self.assertIn("подтверждён OFF", message.answers[-1][0])

    async def test_unconfirmed_off_keeps_active_session_for_fail_closed_control(self):
        app = FakeApp(
            EnableResult(
                enabled=False,
                violations=frozenset({SafetyViolation.OUTPUT_ENABLE_FAILED}),
                detail="output state unknown",
            )
        )
        app.hass.turn_off_result = False
        message = FakeMessage()

        ok = await start_mix_transactional(app, message, PENDING)

        self.assertFalse(ok)
        self.assertTrue(app.charge_controller.is_active)
        self.assertFalse(app.charge_controller.stopped)
        self.assertIn("OFF НЕ подтверждён", message.answers[-1][0])


if __name__ == "__main__":
    unittest.main()
