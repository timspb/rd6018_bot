import copy
import types
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone

from physical_test_control import PhysicalTestControl
from physical_test_control_source_faults import (
    _SOURCE_FAULT_OPS,
    install_physical_test_control_source_faults,
)
from rd6018_telemetry import telemetry_freshness
from runtime_safety import RuntimeSafetyError
from tools.physical_test_source_fault_client import OPERATIONS


@dataclass
class LeaseState:
    generation: int = 50
    armed: bool = True
    remaining_s: float = 899.0
    tripped: bool = False
    boot_quarantine: bool = False
    modbus_age_s: float = 1.0


class FakeLease:
    def __init__(self):
        self.state = LeaseState()
        self.config = types.SimpleNamespace(lease_ttl_s=900.0)

    async def read_state(self):
        return self.state


def fresh_live():
    stamp = datetime.now(timezone.utc).isoformat()
    keys = (
        "battery_voltage",
        "current",
        "temp_ext",
        "temp_int",
        "switch",
        "voltage",
        "protection_code",
        "regulation_code",
    )
    meta = {
        key: {
            "status": "ok",
            "last_reported": stamp,
            "last_updated": stamp,
            "age_s": 0.0,
            "source_key": key,
        }
        for key in keys
    }
    meta["temp_ext"]["source_key"] = "temp_ext_v2"
    meta["switch"]["source_key"] = "output_state_code_v2"
    meta["output_state_code_v2"] = {
        "status": "ok",
        "last_reported": stamp,
        "last_updated": stamp,
        "age_s": 0.0,
        "source_key": "output_state_code_v2",
    }
    for key in ("is_cv", "is_cc"):
        meta[key] = {
            "status": "ok",
            "last_reported": stamp,
            "last_updated": stamp,
            "age_s": 0.0,
            "source_key": "regulation_code",
        }
    return {
        "switch": "on",
        "output_state_code_v2": 1.0,
        "battery_voltage": 12.95,
        "voltage": 12.95,
        "current": 0.17,
        "temp_ext": 27.0,
        "temp_ext_v2": 27.0,
        "temp_int": 32.0,
        "set_voltage": 15.10,
        "set_current": 0.18,
        "ovp": 15.30,
        "ocp": 0.40,
        "protection_code": 0.0,
        "regulation_code": 1.0,
        "is_cv": False,
        "is_cc": True,
        "_meta": meta,
    }


class FreshnessGuard:
    RUNTIME_KEYS = (
        "battery_voltage",
        "current",
        "temp_ext",
        "temp_int",
        "switch",
        "voltage",
        "protection_code",
        "regulation_code",
    )

    def __init__(self):
        self.live = fresh_live()
        self.edge_safety_lease = FakeLease()
        self.output_off_writes = 0
        self.fault_snapshot = None

    async def _raw_live(self):
        return copy.deepcopy(self.live)

    async def get_all_live(self):
        live = await self._raw_live()
        meta = live.get("_meta")
        if not isinstance(meta, dict):
            reason = "critical runtime telemetry freshness metadata is missing"
        else:
            freshness = telemetry_freshness(live, self.RUNTIME_KEYS)
            reason = (
                ""
                if freshness.valid
                else f"critical runtime telemetry is stale/incoherent: {freshness.detail}"
            )
        if reason:
            self.fault_snapshot = copy.deepcopy(live)
            self.output_off_writes += 1
            self.live["switch"] = "off"
            self.live["output_state_code_v2"] = 0.0
            raise RuntimeSafetyError(reason)
        return live


class FakeD061Coordinator:
    def __init__(self, app, guard):
        self.app = app
        self.guard = guard
        self.active = True
        self.off_pending = False
        self.state = "active"
        self.last_status = ""
        self.observe_calls = 0

    async def observe_once(self):
        self.observe_calls += 1
        live = await self.app.hass.get_all_live()
        if live.get("switch") == "off":
            self.active = False
            self.state = "completed"
            self.last_status = "Output became OFF; adopted Manual authority retired"
            lease = self.guard.edge_safety_lease
            lease.state = LeaseState(
                generation=lease.state.generation,
                armed=False,
                remaining_s=0.0,
            )


class FakeD062Coordinator:
    def __init__(self, app, guard):
        self.app = app
        self.guard = guard
        self.active = True
        self.off_pending = False
        self.state = "active"
        self.terminal_reason = ""
        self.last_status = ""
        self.observe_calls = 0

    async def observe_once(self):
        self.observe_calls += 1
        live = await self.app.hass.get_all_live()
        if live.get("switch") == "off":
            self.active = False
            self.state = "completed"
            self.terminal_reason = "OUTPUT_OFF_EXTERNAL"
            self.last_status = "Output became OFF; MIX_ADOPTED authority retired"
            lease = self.guard.edge_safety_lease
            lease.state = LeaseState(
                generation=lease.state.generation,
                armed=False,
                remaining_s=0.0,
            )


class SourceFaultHookTests(unittest.IsolatedAsyncioTestCase):
    def make_system(self):
        app = types.SimpleNamespace()
        guard = FreshnessGuard()
        app.hass = guard
        app.runtime_safety_guard = guard
        app.rd_managed_live_adoption = FakeD061Coordinator(app, guard)
        app.rd_managed_mix_adoption = FakeD062Coordinator(app, guard)
        control = PhysicalTestControl(app, enabled=True)
        install_physical_test_control_source_faults(app, control)
        return app, guard, control

    async def test_d061_stale_temp_preserves_numeric_value_and_fails_closed(self):
        app, guard, control = self.make_system()
        before_temp = guard.live["temp_ext"]
        response = await control.dispatch({"op": "d061_fault_stale_temp_source"})
        self.assertTrue(response["ok"], response)
        result = response["result"]
        self.assertTrue(result["contained"])
        self.assertEqual(result["hardware_writes_injected"], 0)
        self.assertIn("temp_ext stale", result["reason"])
        self.assertEqual(guard.fault_snapshot["temp_ext"], before_temp)
        self.assertEqual(
            guard.fault_snapshot["_meta"]["temp_ext"]["source_key"], "temp_ext_v2"
        )
        self.assertEqual(
            guard.fault_snapshot["_meta"]["temp_ext"]["last_reported"],
            "2000-01-01T00:00:00+00:00",
        )
        self.assertNotEqual(
            guard.live["_meta"]["temp_ext"]["last_reported"],
            "2000-01-01T00:00:00+00:00",
        )
        self.assertEqual(guard.output_off_writes, 1)
        self.assertEqual(app.rd_managed_live_adoption.observe_calls, 2)
        self.assertEqual(result["output"], "off")
        self.assertFalse(result["lease_armed"])
        self.assertEqual(result["remaining_s"], 0.0)

    async def test_d061_stale_output_only_corrupts_decision_heartbeat(self):
        _app, guard, control = self.make_system()
        response = await control.dispatch({"op": "d061_fault_stale_output_source"})
        self.assertTrue(response["ok"], response)
        result = response["result"]
        self.assertIn("switch stale", result["reason"])
        self.assertEqual(guard.fault_snapshot["switch"], "on")
        self.assertEqual(guard.fault_snapshot["output_state_code_v2"], 1.0)
        self.assertEqual(
            guard.fault_snapshot["_meta"]["switch"]["source_key"],
            "output_state_code_v2",
        )
        # The authoritative raw register-18 metadata itself is not poisoned; real
        # post-command OFF confirmation remains able to use it.
        self.assertNotEqual(
            guard.fault_snapshot["_meta"]["output_state_code_v2"]["last_reported"],
            "2000-01-01T00:00:00+00:00",
        )
        self.assertEqual(result["output_state_code_v2"], 0.0)
        self.assertFalse(result["lease_armed"])

    async def test_d061_stale_vout_preserves_voltage_and_fails_closed(self):
        _app, guard, control = self.make_system()
        before_vout = guard.live["voltage"]
        response = await control.dispatch({"op": "d061_fault_stale_vout_source"})
        self.assertTrue(response["ok"], response)
        self.assertEqual(guard.fault_snapshot["voltage"], before_vout)
        self.assertIn("voltage stale", response["result"]["reason"])
        self.assertEqual(guard.output_off_writes, 1)
        self.assertFalse(response["result"]["lease_armed"])

    async def test_d061_missing_meta_preserves_numeric_snapshot_and_fails_closed(self):
        _app, guard, control = self.make_system()
        expected = {
            key: guard.live[key]
            for key in ("battery_voltage", "current", "temp_ext", "voltage", "set_voltage")
        }
        response = await control.dispatch({"op": "d061_fault_missing_runtime_meta"})
        self.assertTrue(response["ok"], response)
        self.assertNotIn("_meta", guard.fault_snapshot)
        for key, value in expected.items():
            self.assertEqual(guard.fault_snapshot[key], value)
        self.assertIn(
            "freshness metadata is missing", response["result"]["reason"]
        )
        self.assertFalse(response["result"]["lease_armed"])

    async def test_d062_stale_regulation_keeps_mode_values_coherent(self):
        app, guard, control = self.make_system()
        app.rd_managed_live_adoption.active = False
        response = await control.dispatch(
            {"op": "d062_fault_stale_regulation_source"}
        )
        self.assertTrue(response["ok"], response)
        result = response["result"]
        self.assertIn("regulation_code stale", result["reason"])
        snapshot = guard.fault_snapshot
        self.assertEqual(snapshot["regulation_code"], 1.0)
        self.assertFalse(snapshot["is_cv"])
        self.assertTrue(snapshot["is_cc"])
        for key in ("regulation_code", "is_cv", "is_cc"):
            self.assertEqual(
                snapshot["_meta"][key]["last_reported"],
                "2000-01-01T00:00:00+00:00",
            )
        self.assertEqual(snapshot["_meta"]["is_cv"]["source_key"], "regulation_code")
        self.assertEqual(snapshot["_meta"]["is_cc"]["source_key"], "regulation_code")
        self.assertEqual(app.rd_managed_mix_adoption.observe_calls, 2)
        self.assertFalse(result["lease_armed"])
        self.assertEqual(result["hardware_writes_injected"], 0)

    async def test_inactive_authority_rejects_read_only(self):
        app, guard, control = self.make_system()
        app.rd_managed_live_adoption.active = False
        for operation in (
            "d061_fault_stale_temp_source",
            "d061_fault_stale_output_source",
            "d061_fault_stale_vout_source",
            "d061_fault_missing_runtime_meta",
        ):
            response = await control.dispatch({"op": operation})
            self.assertFalse(response["ok"], (operation, response))
        app.rd_managed_mix_adoption.active = False
        response = await control.dispatch(
            {"op": "d062_fault_stale_regulation_source"}
        )
        self.assertFalse(response["ok"], response)
        self.assertEqual(guard.output_off_writes, 0)
        self.assertEqual(guard.live["switch"], "on")

    async def test_source_faults_reject_extra_fields_and_client_surface_is_typed(self):
        _app, guard, control = self.make_system()
        response = await control.dispatch(
            {"op": "d061_fault_stale_temp_source", "entity_id": "sensor.fake"}
        )
        self.assertFalse(response["ok"])
        response = await control.dispatch(
            {"op": "d062_fault_stale_regulation_source", "age_s": 999999}
        )
        self.assertFalse(response["ok"])
        self.assertEqual(guard.output_off_writes, 0)
        self.assertEqual(OPERATIONS, _SOURCE_FAULT_OPS)


if __name__ == "__main__":
    unittest.main()
