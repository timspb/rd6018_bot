import asyncio
import inspect
import unittest
from types import SimpleNamespace
from pathlib import Path

from application.execution_intent.models import ExecutionIntent, SafetyContext
from application.execution_port import ExecutionPort


class Owner:
    def __init__(self):
        self.calls = []
        self.live = {
            "switch": "on",
            "battery_voltage": 13.0,
            "_meta": {
                "set_voltage_readback_v2": {"status": "ok", "age_s": 0.0},
                "set_current_readback_v2": {"status": "ok", "age_s": 0.0},
            },
            "set_voltage_readback_v2": 14.1,
            "set_current_readback_v2": 0.9,
        }

    async def get_all_live(self):
        return dict(self.live)

    async def set_current(self, value):
        self.calls.append(("set_current", value))
        self.live["set_current_readback_v2"] = value
        return True

    async def set_voltage(self, value):
        self.calls.append(("set_voltage", value))
        self.live["set_voltage_readback_v2"] = value
        return True

    async def turn_off(self):
        self.calls.append(("turn_off",))
        self.live["switch"] = "off"
        return True


def intent(mode="MANUAL_MIX_SETPOINT"):
    return ExecutionIntent(
        requested_voltage_v=15.1 if mode != "MANUAL_STOP" else 0.0,
        requested_current_a=0.9 if mode != "MANUAL_STOP" else 0.0,
        requested_mode=mode,
        source_decision_id="decision-1",
        safety_context=SafetyContext(telemetry_state="FRESH", verification_state="REQUIRED"),
    )


class ExecutionPlaneTests(unittest.TestCase):
    def test_execution_intent_is_required_for_setpoint_write(self):
        port = ExecutionPort(Owner())
        with self.assertRaises(AttributeError):
            asyncio.run(port.apply_intent(SimpleNamespace(), identity=SimpleNamespace(session_id="s", trace_id="t")))

    def test_v2_owner_is_the_only_injected_write_target(self):
        owner = Owner()
        port = ExecutionPort(owner)
        result = asyncio.run(port.apply_intent(intent(), identity=SimpleNamespace(session_id="s", trace_id="t")))
        self.assertTrue(result.verified)
        self.assertEqual([name for name, *_ in owner.calls], ["set_current", "set_voltage"])
        self.assertEqual(port.audit[-1].session_id, "s")
        self.assertEqual(port.audit[-1].trace_id, "t")

    def test_disable_is_verified_and_correlated(self):
        owner = Owner()
        port = ExecutionPort(owner)
        result = asyncio.run(port.disable(intent("MANUAL_STOP"), identity=SimpleNamespace(session_id="s", trace_id="t")))
        self.assertTrue(result.verified)
        self.assertEqual(owner.calls, [("turn_off",)])

    def test_manual_mode_has_no_direct_setpoint_or_hardware_owner_calls(self):
        source = inspect.getsource(__import__("manual_mode"))
        self.assertNotIn("self.app.hass.set_current", source)
        self.assertNotIn("self.app.hass.set_voltage", source)
        self.assertNotIn("self.app.hass.safe_enable_output", source)
        self.assertNotIn("self.app.hass.turn_off", source)

    def test_production_entrypoint_does_not_import_new_physical_owner(self):
        source = Path("bot.py").read_text(encoding="utf-8")
        self.assertNotIn("runtime.physical", source)
        self.assertNotIn("runtime.output", source)


if __name__ == "__main__":
    unittest.main()
