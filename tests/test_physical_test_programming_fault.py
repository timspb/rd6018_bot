import copy
import types
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone

from physical_test_control import PhysicalTestControl
from physical_test_control_source_faults import (
    _PROGRAMMED_READBACK_OPS,
    install_physical_test_control_source_faults,
)
from safe_output import (
    OutputRequest,
    SafeOutputCoordinator,
    SafetySupervisor,
)
from tools.physical_test_programming_fault_client import OPERATION


STALE = "2000-01-01T00:00:00+00:00"


def _fresh_stamp():
    return datetime.now(timezone.utc).isoformat()


def _meta(ts, *, source_key=None):
    return {
        "status": "ok",
        "last_reported": ts,
        "last_updated": ts,
        "age_s": 0.0 if ts != STALE else 1_000_000_000.0,
        "source_key": source_key,
    }


def idle_live(*, set_voltage_stale=True):
    fresh = _fresh_stamp()
    static = STALE if set_voltage_stale else fresh
    live = {
        "switch": "off",
        "output_state_code_v2": 0.0,
        "battery_voltage": 12.80,
        "voltage": 0.0,
        "current": 0.0,
        "temp_ext": 25.0,
        "temp_int": 31.0,
        "input_voltage": 65.0,
        "set_voltage": 15.10,
        "set_current": 0.18,
        "ovp": 15.30,
        "ocp": 0.40,
        "protection_code": 0.0,
        "regulation_code": 0.0,
        "is_cv": True,
        "is_cc": False,
    }
    live["_meta"] = {
        "switch": _meta(fresh, source_key="output_state_code_v2"),
        "output_state_code_v2": _meta(fresh, source_key="output_state_code_v2"),
        "battery_voltage": _meta(fresh, source_key="battery_voltage"),
        "voltage": _meta(STALE, source_key="voltage"),
        "current": _meta(fresh, source_key="current"),
        "temp_ext": _meta(fresh, source_key="temp_ext_v2"),
        "temp_int": _meta(fresh, source_key="temp_int_v2"),
        "protection_code": _meta(fresh, source_key="protection_code"),
        "set_voltage": _meta(static, source_key="set_voltage"),
        "set_current": _meta(STALE, source_key="set_current"),
        "ovp": _meta(STALE, source_key="ovp"),
        "ocp": _meta(STALE, source_key="ocp"),
    }
    return live


@dataclass
class LeaseState:
    generation: int = 21
    armed: bool = False
    remaining_s: float = 0.0
    tripped: bool = False
    boot_quarantine: bool = False
    modbus_age_s: float = 1.0


class FakeLease:
    def __init__(self):
        self.state = LeaseState()
        self.config = types.SimpleNamespace(lease_ttl_s=900.0)

    async def read_state(self):
        return self.state


class FakeAdapter:
    def __init__(self, *, set_voltage_stale=True, bypass_readback_gate=False, wrong_write=False):
        self.live = idle_live(set_voltage_stale=set_voltage_stale)
        self.hardware_writes = []
        self.hardware_on_calls = 0
        self.hardware_off_calls = 0
        self.bypass_readback_gate = bypass_readback_gate
        self.wrong_write = wrong_write

    async def get_all_live(self):
        return copy.deepcopy(self.live)

    def _write(self, key, value):
        value = float(value)
        self.hardware_writes.append((key, value))
        self.live[key] = value
        stamp = _fresh_stamp()
        self.live["_meta"][key]["last_reported"] = stamp
        self.live["_meta"][key]["last_updated"] = stamp
        self.live["_meta"][key]["age_s"] = 0.0
        return True

    async def set_ovp(self, value):
        return self._write("ovp", value)

    async def set_ocp(self, value):
        return self._write("ocp", value)

    async def set_voltage(self, value):
        return self._write("set_voltage", value)

    async def set_current(self, value):
        return self._write("set_current", value)

    async def turn_on(self, _entity_id=None):
        self.hardware_on_calls += 1
        self.live["switch"] = "on"
        self.live["output_state_code_v2"] = 1.0
        return True

    async def turn_off(self, _entity_id=None):
        self.hardware_off_calls += 1
        self.live["switch"] = "off"
        self.live["output_state_code_v2"] = 0.0
        return True

    async def safe_enable_output(
        self,
        *,
        voltage_v,
        current_a,
        ovp_v,
        ocp_a,
        recipe_voltage_ceiling_v,
        **_kwargs,
    ):
        if self.wrong_write:
            await self.set_ovp(ovp_v)
            await self.set_ocp(ocp_a)
            await self.set_voltage(float(voltage_v) + 0.10)
            raise AssertionError("harness should have blocked wrong write")
        request = OutputRequest(
            float(voltage_v),
            float(current_a),
            float(ovp_v),
            float(ocp_a),
            float(recipe_voltage_ceiling_v),
        )
        if self.bypass_readback_gate:
            await self.set_ovp(ovp_v)
            await self.set_ocp(ocp_a)
            await self.set_voltage(voltage_v)
            await self.set_current(current_a)
            try:
                await self.turn_on()
            except Exception:
                await self.turn_off()
            return types.SimpleNamespace(
                enabled=False,
                violations=frozenset(),
                detail="synthetic bypass",
            )
        coordinator = SafeOutputCoordinator(
            self,
            SafetySupervisor(),
            readback_timeout_s=0.0,
        )
        return await coordinator.enable(request)


class FakeGuard:
    READBACK_TOLERANCE = 0.08

    def __init__(self, adapter):
        self.adapter = adapter
        self.edge_safety_lease = FakeLease()
        self._off_unconfirmed = False

    async def _raw_live(self):
        return copy.deepcopy(self.adapter.live)


class ProgrammedReadbackPhysicalHookTests(unittest.IsolatedAsyncioTestCase):
    def make_system(self, **adapter_kwargs):
        app = types.SimpleNamespace()
        adapter = FakeAdapter(**adapter_kwargs)
        guard = FakeGuard(adapter)
        app.hass = adapter
        app.runtime_safety_guard = guard
        app.rd_control_mode_manager = types.SimpleNamespace(
            pb_managed=True,
            release_in_progress=False,
        )
        app.charge_controller = types.SimpleNamespace(is_active=False)
        app.manual_session_manager = types.SimpleNamespace(is_active=False)
        app.rd_managed_live_adoption = types.SimpleNamespace(active=False, off_pending=False)
        app.rd_managed_mix_adoption = types.SimpleNamespace(active=False, off_pending=False)
        control = PhysicalTestControl(app, enabled=True)
        install_physical_test_control_source_faults(app, control)
        return app, adapter, guard, control

    async def test_b16_holds_only_post_write_vset_freshness_and_never_attempts_on(self):
        _app, adapter, _guard, control = self.make_system()
        before = {
            key: adapter.live[key]
            for key in ("set_voltage", "set_current", "ovp", "ocp")
        }
        response = await control.dispatch({"op": OPERATION})
        self.assertTrue(response["ok"], response)
        result = response["result"]
        self.assertTrue(result["blocked_before_output_on"])
        self.assertIn("telemetry_invalid", result["violations"])
        self.assertIn("programmed readback telemetry missing/invalid", result["detail"])
        self.assertEqual(result["output_on_attempts"], 0)
        self.assertEqual(result["output_off_attempts"], 1)
        self.assertEqual(
            result["programming_writes"],
            {"ovp": 1, "ocp": 1, "set_voltage": 1, "set_current": 1},
        )
        self.assertEqual(adapter.hardware_on_calls, 0)
        self.assertEqual(adapter.hardware_off_calls, 1)
        self.assertEqual(
            adapter.hardware_writes,
            [
                ("ovp", before["ovp"]),
                ("ocp", before["ocp"]),
                ("set_voltage", before["set_voltage"]),
                ("set_current", before["set_current"]),
            ],
        )
        for key, value in before.items():
            self.assertEqual(adapter.live[key], value)
        self.assertEqual(adapter.live["switch"], "off")
        self.assertFalse(result["lease_armed"])
        self.assertTrue(result["real_set_voltage_fresh_after"])
        self.assertEqual(result["hardware_value_changes_expected"], 0)

    async def test_b16_requires_real_idle_staleness_before_any_write(self):
        _app, adapter, _guard, control = self.make_system(set_voltage_stale=False)
        response = await control.dispatch({"op": OPERATION})
        self.assertFalse(response["ok"], response)
        self.assertIn("already stale idle set_voltage heartbeat", response["error"])
        self.assertEqual(adapter.hardware_writes, [])
        self.assertEqual(adapter.hardware_on_calls, 0)
        self.assertEqual(adapter.hardware_off_calls, 0)

    async def test_b16_safety_barrier_blocks_unexpected_value_change(self):
        _app, adapter, _guard, control = self.make_system(wrong_write=True)
        response = await control.dispatch({"op": OPERATION})
        self.assertFalse(response["ok"], response)
        self.assertIn("blocked unexpected set_voltage write", response["error"])
        self.assertEqual(adapter.hardware_on_calls, 0)
        self.assertEqual(adapter.live["set_voltage"], 15.10)
        self.assertEqual(
            adapter.hardware_writes,
            [("ovp", 15.30), ("ocp", 0.40)],
        )

    async def test_b16_detects_attempt_to_cross_output_on_boundary_without_actuating(self):
        _app, adapter, _guard, control = self.make_system(bypass_readback_gate=True)
        response = await control.dispatch({"op": OPERATION})
        self.assertFalse(response["ok"], response)
        self.assertIn("reached Output ON", response["error"])
        self.assertEqual(adapter.hardware_on_calls, 0)
        self.assertEqual(adapter.live["switch"], "off")
        self.assertEqual(adapter.hardware_off_calls, 1)

    async def test_b16_request_surface_accepts_no_values_or_entities(self):
        _app, adapter, _guard, control = self.make_system()
        for extra in (
            {"voltage": 12.0},
            {"entity_id": "number.fake"},
            {"timestamp": STALE},
        ):
            response = await control.dispatch({"op": OPERATION, **extra})
            self.assertFalse(response["ok"], (extra, response))
        self.assertEqual(adapter.hardware_writes, [])
        self.assertEqual(_PROGRAMMED_READBACK_OPS, {OPERATION})


if __name__ == "__main__":
    unittest.main()
