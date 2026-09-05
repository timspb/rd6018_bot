import copy
import types
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from unittest.mock import patch

from physical_test_control import PhysicalTestControl
from physical_test_control_programmed_readback_v2 import (
    OPERATION,
    install_physical_test_control_programmed_readback_v2,
)
from physical_test_control_source_faults import install_physical_test_control_source_faults
from safe_output import OutputRequest, SafeOutputCoordinator, SafetySupervisor


def _fresh_stamp():
    return datetime.now(timezone.utc).isoformat()


def _meta(source_key):
    stamp = _fresh_stamp()
    return {
        "status": "ok",
        "last_reported": stamp,
        "last_updated": stamp,
        "age_s": 0.0,
        "source_key": source_key,
    }


def idle_live():
    live = {
        "switch": "off",
        "output_state_code_v2": 0.0,
        "battery_voltage": 12.8,
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
    }
    live["_meta"] = {
        "switch": _meta("output_state_code_v2"),
        "output_state_code_v2": _meta("output_state_code_v2"),
        "battery_voltage": _meta("battery_voltage"),
        "voltage": _meta("voltage"),
        "current": _meta("current"),
        "temp_ext": _meta("temp_ext_v2"),
        "temp_int": _meta("temp_int_v2"),
        "protection_code": _meta("protection_code"),
        "set_voltage": _meta("set_voltage_readback_v2"),
        "set_current": _meta("set_current_readback_v2"),
        "ovp": _meta("ovp_readback_v2"),
        "ocp": _meta("ocp_readback_v2"),
    }
    return live


@dataclass
class LeaseState:
    generation: int = 31
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
    def __init__(self, *, refresh_readback=True):
        self.live = idle_live()
        self.refresh_readback = refresh_readback
        self.hardware_writes = []
        self.hardware_on_calls = 0
        self.hardware_off_calls = 0
        self._programmed = False

    async def get_all_live(self):
        if self._programmed and self.refresh_readback:
            stamp = _fresh_stamp()
            for key in ("set_voltage", "set_current", "ovp", "ocp"):
                self.live["_meta"][key]["last_reported"] = stamp
                self.live["_meta"][key]["last_updated"] = stamp
                self.live["_meta"][key]["age_s"] = 0.0
        return copy.deepcopy(self.live)

    def _write(self, key, value):
        value = float(value)
        self.hardware_writes.append((key, value))
        self.live[key] = value
        if key == "set_current":
            self._programmed = True
        # Deliberately do NOT update canonical metadata here. In production the
        # writable number entity is not the safety heartbeat; the independent V2
        # Modbus sensor owns that heartbeat.
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
        coordinator = SafeOutputCoordinator(
            self,
            SafetySupervisor(),
            readback_timeout_s=0.0,
        )
        return await coordinator.enable(
            OutputRequest(
                float(voltage_v),
                float(current_a),
                float(ovp_v),
                float(ocp_a),
                float(recipe_voltage_ceiling_v),
            )
        )


class FakeGuard:
    READBACK_TOLERANCE = 0.08

    def __init__(self, adapter):
        self.adapter = adapter
        self.edge_safety_lease = FakeLease()
        self._off_unconfirmed = False

    async def _raw_live(self):
        return await self.adapter.get_all_live()


class ProgrammedReadbackV2PhysicalHookTests(unittest.IsolatedAsyncioTestCase):
    def make_system(self, *, refresh_readback=True):
        app = types.SimpleNamespace()
        adapter = FakeAdapter(refresh_readback=refresh_readback)
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
        # Production composition installs the legacy/source-fault extension first, then
        # the authoritative readback B16 shadow.
        install_physical_test_control_source_faults(app, control)
        install_physical_test_control_programmed_readback_v2(app, control)
        return app, adapter, guard, control

    async def test_b16_uses_authoritative_force_updated_readback_and_never_attempts_on(self):
        _app, adapter, _guard, control = self.make_system()
        before = {key: adapter.live[key] for key in ("set_voltage", "set_current", "ovp", "ocp")}
        before_ts = adapter.live["_meta"]["set_voltage"]["last_reported"]
        response = await control.dispatch({"op": OPERATION})
        self.assertTrue(response["ok"], response)
        result = response["result"]
        self.assertTrue(result["blocked_before_output_on"])
        self.assertIn("telemetry_invalid", result["violations"])
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
        self.assertEqual(result["set_voltage_source_key"], "set_voltage_readback_v2")
        self.assertEqual(result["set_voltage_last_reported_before"], before_ts)
        self.assertNotEqual(result["set_voltage_last_reported_after"], before_ts)
        self.assertTrue(result["set_voltage_heartbeat_advanced"])
        self.assertFalse(result["lease_armed"])
        self.assertEqual(adapter.live["switch"], "off")

    async def test_number_write_without_readback_heartbeat_cannot_prove_b16(self):
        _app, adapter, _guard, control = self.make_system(refresh_readback=False)
        with patch(
            "physical_test_control_programmed_readback_v2._B16_REAL_READBACK_PROOF_TIMEOUT_S",
            0.01,
        ):
            response = await control.dispatch({"op": OPERATION})
        self.assertFalse(response["ok"], response)
        self.assertIn("set_voltage_readback_v2 heartbeat did not advance", response["error"])
        self.assertEqual(adapter.hardware_on_calls, 0)
        self.assertEqual(adapter.hardware_off_calls, 1)
        self.assertEqual(adapter.live["switch"], "off")

    async def test_b16_rejects_wrong_or_stale_canonical_readback_before_writes(self):
        for mutation in ("wrong_source", "stale"):
            with self.subTest(mutation=mutation):
                _app, adapter, _guard, control = self.make_system()
                if mutation == "wrong_source":
                    adapter.live["_meta"]["set_voltage"]["source_key"] = "set_voltage"
                else:
                    adapter.live["_meta"]["set_voltage"]["last_reported"] = "2000-01-01T00:00:00+00:00"
                    adapter.live["_meta"]["set_voltage"]["last_updated"] = "2000-01-01T00:00:00+00:00"
                response = await control.dispatch({"op": OPERATION})
                self.assertFalse(response["ok"], response)
                self.assertEqual(adapter.hardware_writes, [])
                self.assertEqual(adapter.hardware_on_calls, 0)

    async def test_b16_request_accepts_no_authority_widening_fields(self):
        _app, adapter, _guard, control = self.make_system()
        for extra in (
            {"voltage": 12.0},
            {"entity_id": "number.fake"},
            {"timestamp": "2000-01-01T00:00:00Z"},
        ):
            response = await control.dispatch({"op": OPERATION, **extra})
            self.assertFalse(response["ok"], (extra, response))
        self.assertEqual(adapter.hardware_writes, [])


if __name__ == "__main__":
    unittest.main()
