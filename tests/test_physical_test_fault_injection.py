import asyncio
import types
import unittest
from enum import Enum
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from battery_registry import BatteryRecord
from pb_domain import BatteryChemistry, BatteryCondition, BatteryIdentity, BatteryLifecycle
from physical_test_control import _FAULT_OPS, _OPS, PhysicalTestControl
from tools.physical_test_control_client import OPERATIONS


class Mode(str, Enum):
    HANDS_OFF = "hands_off"
    PB_MANAGED = "pb_managed"


class FakeLease:
    def __init__(self):
        self.config = SimpleNamespace(lease_ttl_s=900.0, ack_attempts=3)
        self.state = SimpleNamespace(
            armed=False,
            tripped=False,
            boot_quarantine=False,
            generation=10,
            remaining_s=0.0,
            modbus_age_s=1.0,
        )
        self.presses = []

    async def read_state(self):
        return self.state

    async def _press(self, entity_id):
        self.presses.append(entity_id)
        # Real live-adopt edge ownership changes before Python receives a positive ACK.
        self.state = SimpleNamespace(
            armed=True,
            tripped=False,
            boot_quarantine=False,
            generation=11,
            remaining_s=900.0,
            modbus_age_s=1.0,
        )
        return True


class FakeGuard:
    def __init__(self, live):
        self.live = live
        self.edge_safety_lease = FakeLease()
        self.coordinator = None

    async def _raw_live(self):
        return dict(self.live)

    async def get_all_live(self):
        # Model the production StrictRuntimeSafetyGuard renewal boundary. The injected
        # raw-protection error forces verified physical OFF and then propagates.
        await self.coordinator.edge._require_raw_protection_normal()
        return dict(self.live)


class FakeManager:
    def __init__(self):
        self.mode = Mode.HANDS_OFF

    @property
    def hands_off(self):
        return self.mode is Mode.HANDS_OFF


class FakeEdge:
    def __init__(self, lease):
        self.lease = lease
        self.config = SimpleNamespace(entity="button.edge_adopt_live")
        self.command_may_have_executed = False

    async def _require_raw_protection_normal(self):
        return None


class FakeCoordinator:
    def __init__(self, app):
        self.app = app
        self.guard = app.runtime_safety_guard
        self.edge = FakeEdge(self.guard.edge_safety_lease)
        self.active = False
        self.state = "idle"
        self.max_authority = None
        self.current_authority = None
        self.poll_s = -1.0
        self.adopt_mode = "toctou"

    @staticmethod
    def fingerprint_from_live(live):
        return SimpleNamespace(
            set_voltage_v=float(live["set_voltage"]),
            set_current_a=float(live["set_current"]),
            ovp_v=float(live["ovp"]),
            ocp_a=float(live["ocp"]),
        )

    async def adopt(self, preview):
        if self.adopt_mode == "toctou":
            first = self.fingerprint_from_live(await self.guard._raw_live())
            self.assert_same(preview.fingerprint, first)
            second = self.fingerprint_from_live(await self.guard._raw_live())
            self.assert_same(preview.fingerprint, second)
            raise AssertionError("TOCTOU test did not inject a mismatch")

        if self.adopt_mode == "ambiguous":
            before = await self.edge.lease.read_state()
            self.edge.command_may_have_executed = True
            accepted = await self.edge.lease._press(self.edge.config.entity)
            if not accepted:
                raise RuntimeError("synthetic edge command rejected")
            for _ in range(int(self.edge.lease.config.ack_attempts)):
                latest = await self.edge.lease.read_state()
                if latest.generation != before.generation:
                    raise AssertionError("ACK hiding failed")
            # Model the existing coordinator command-uncertainty containment. No
            # setpoint/protection write occurs: only Output is forced OFF and lease is
            # retired after the hidden ACK window is exhausted.
            self.guard.live["switch"] = "off"
            self.guard.live["output_state_code_v2"] = 0.0
            self.edge.lease.state = SimpleNamespace(
                armed=False,
                tripped=False,
                boot_quarantine=False,
                generation=11,
                remaining_s=0.0,
                modbus_age_s=1.0,
            )
            self.state = "failed"
            raise RuntimeError("edge live adoption was not positively acknowledged by generation/readback")

        raise AssertionError(f"unknown adopt mode: {self.adopt_mode}")

    @staticmethod
    def assert_same(expected, actual):
        values = (
            (expected.set_voltage_v, actual.set_voltage_v),
            (expected.set_current_a, actual.set_current_a),
            (expected.ovp_v, actual.ovp_v),
            (expected.ocp_a, actual.ocp_a),
        )
        if any(abs(float(left) - float(right)) > 0.06 for left, right in values):
            raise RuntimeError("live RD setpoints changed during adoption; authority was not transferred")

    async def observe_once(self):
        if self.guard.live["switch"] == "off":
            self.active = False
            self.state = "completed"
            self.edge.lease.state = SimpleNamespace(
                armed=False,
                tripped=False,
                boot_quarantine=False,
                generation=self.edge.lease.state.generation,
                remaining_s=0.0,
                modbus_age_s=1.0,
            )


class RawProtectionGuard(FakeGuard):
    def __init__(self, live):
        super().__init__(live)
        self.background_gate_completed = False

    async def get_all_live(self):
        try:
            # A production observer/renewal task may enter the shared edge gate while
            # the control request is waiting on I/O. It must continue through the real
            # gate rather than consuming the one-shot injected failure.
            background = asyncio.create_task(
                self.coordinator.edge._require_raw_protection_normal()
            )
            await background
            self.background_gate_completed = True
            await self.coordinator.edge._require_raw_protection_normal()
        except Exception:
            # This is the strict fail-closed effect being exercised by the hook.
            self.live["switch"] = "off"
            self.live["output_state_code_v2"] = 0.0
            raise
        return dict(self.live)


class FakeApp:
    def __init__(self, *, raw_protection=False):
        live = {
            "switch": "on",
            "output_state_code_v2": 1.0,
            "set_voltage": 13.6,
            "set_current": 0.2,
            "ovp": 13.8,
            "ocp": 0.4,
            "protection_code": 0.0,
            "protection_status": "normal",
            "_meta": {
                "switch": {"age_s": 1.0, "source_key": "output_state_code_v2"},
                "protection_code": {"age_s": 1.0},
            },
        }
        guard_type = RawProtectionGuard if raw_protection else FakeGuard
        self.runtime_safety_guard = guard_type(live)
        self.rd_control_mode_manager = FakeManager()
        self.rd_managed_live_adoption = FakeCoordinator(self)
        self.runtime_safety_guard.coordinator = self.rd_managed_live_adoption
        self.manual_session_manager = SimpleNamespace(state="idle")


def battery_record():
    return BatteryRecord(
        identity=BatteryIdentity(
            battery_id="varta_agm80_a0019828108",
            chemistry=BatteryChemistry.AGM,
            nominal_capacity_ah=80.0,
            manufacturer="Varta",
            model="Mercedes A 001 982 81 08",
        ),
        lifecycle=BatteryLifecycle(condition=BatteryCondition.UNKNOWN, cca_a=800.0),
    )


class PhysicalTestFaultInjectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_toctou_is_read_only_and_stops_before_edge_command(self):
        app = FakeApp()
        control = PhysicalTestControl(app, enabled=True)
        before = dict(app.runtime_safety_guard.live)
        with patch("physical_test_control.get_battery", new=AsyncMock(return_value=battery_record())):
            response = await control.dispatch(
                {
                    "op": "d061_fault_toctou_precommand",
                    "battery_id": "varta_agm80_a0019828108",
                }
            )
        self.assertTrue(response["ok"], response)
        result = response["result"]
        self.assertTrue(result["rejected"])
        self.assertFalse(result["command_may_have_executed"])
        self.assertEqual(result["generation_before"], 10)
        self.assertEqual(result["generation_after"], 10)
        self.assertEqual(result["output"], "on")
        self.assertEqual(result["hardware_writes_injected"], 0)
        self.assertEqual(app.runtime_safety_guard.edge_safety_lease.presses, [])
        self.assertEqual(app.runtime_safety_guard.live, before)

    async def test_ambiguous_ack_sends_one_real_edge_command_then_contains_off(self):
        app = FakeApp()
        app.rd_managed_live_adoption.adopt_mode = "ambiguous"
        control = PhysicalTestControl(app, enabled=True)
        with patch("physical_test_control.get_battery", new=AsyncMock(return_value=battery_record())):
            response = await control.dispatch(
                {
                    "op": "d061_fault_ambiguous_edge_ack",
                    "battery_id": "varta_agm80_a0019828108",
                }
            )
        self.assertTrue(response["ok"], response)
        result = response["result"]
        self.assertTrue(result["contained"])
        self.assertTrue(result["command_may_have_executed"])
        self.assertEqual(result["generation_before"], 10)
        self.assertEqual(result["generation_after"], 11)
        self.assertEqual(result["output"], "off")
        self.assertFalse(result["lease_armed"])
        self.assertEqual(result["remaining_s"], 0.0)
        self.assertEqual(
            app.runtime_safety_guard.edge_safety_lease.presses,
            ["button.edge_adopt_live"],
        )
        self.assertEqual(app.runtime_safety_guard.live["set_voltage"], 13.6)
        self.assertEqual(app.runtime_safety_guard.live["set_current"], 0.2)
        self.assertEqual(app.runtime_safety_guard.live["ovp"], 13.8)
        self.assertEqual(app.runtime_safety_guard.live["ocp"], 0.4)

    async def test_raw_protection_unavailable_uses_existing_gate_and_retires_off(self):
        app = FakeApp(raw_protection=True)
        coordinator = app.rd_managed_live_adoption
        coordinator.active = True
        coordinator.state = "active"
        coordinator.edge.lease.state = SimpleNamespace(
            armed=True,
            tripped=False,
            boot_quarantine=False,
            generation=12,
            remaining_s=899.0,
            modbus_age_s=1.0,
        )
        control = PhysicalTestControl(app, enabled=True)
        response = await control.dispatch({"op": "d061_fault_raw_protection_unavailable"})
        self.assertTrue(response["ok"], response)
        result = response["result"]
        self.assertTrue(result["contained"])
        self.assertIn("physical-test injected raw RD6018 protection-code unavailable", result["reason"])
        self.assertTrue(app.runtime_safety_guard.background_gate_completed)
        self.assertEqual(result["output"], "off")
        self.assertFalse(result["lease_armed"])
        self.assertEqual(result["remaining_s"], 0.0)
        self.assertFalse(coordinator.active)
        self.assertEqual(app.runtime_safety_guard.live["protection_code"], 0.0)

    async def test_fault_operations_reject_arbitrary_widening_parameters(self):
        app = FakeApp()
        control = PhysicalTestControl(app, enabled=True)
        response = await control.dispatch(
            {
                "op": "d061_fault_toctou_precommand",
                "battery_id": "varta_agm80_a0019828108",
                "set_current": 9.0,
            }
        )
        self.assertFalse(response["ok"])
        response = await control.dispatch(
            {"op": "d061_fault_raw_protection_unavailable", "entity_id": "sensor.fake"}
        )
        self.assertFalse(response["ok"])

    def test_fault_surface_is_separate_and_client_has_only_typed_operations(self):
        self.assertEqual(
            _FAULT_OPS,
            {
                "d061_fault_toctou_precommand",
                "d061_fault_ambiguous_edge_ack",
                "d061_fault_raw_protection_unavailable",
            },
        )
        self.assertTrue(_OPS.isdisjoint(_FAULT_OPS))
        self.assertEqual(OPERATIONS, _OPS | _FAULT_OPS)


if __name__ == "__main__":
    unittest.main()
