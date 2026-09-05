import asyncio
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from diagnostic_persistence import DiagnosticActionJournal, DiagnosticActionKind, DiagnosticActionStatus
from pb_domain import BatteryChemistry
from physical_test_control_diagnostic import PhysicalTestControlDiagnostic


class FakeLease:
    def __init__(self):
        self.armed = False
        self.tripped = False
        self.boot_quarantine = False
        self.generation = 7
        self.modbus_age_s = 1.0
        self.remaining_s = 0.0


class FakeHass:
    def __init__(self, lease):
        self.lease = lease
        self.output_on = False
        self.set_voltage_value = 15.10
        self.set_current_value = 0.18
        self.ovp_value = 15.30
        self.ocp_value = 0.40
        self.set_current_calls = []
        self.turn_off_calls = 0

    async def get_all_live(self):
        return {
            "switch": "on" if self.output_on else "off",
            "output_state_code_v2": 1 if self.output_on else 0,
            "protection_code": 0,
            "temp_ext": 25.0,
            "temp_int": 30.0,
            "battery_voltage": 12.90 if self.output_on else 12.85,
            "voltage": 12.90 if self.output_on else 0.0,
            "current": min(self.set_current_value, 0.17) if self.output_on else 0.0,
            "set_voltage": self.set_voltage_value,
            "set_current": self.set_current_value,
            "set_current_readback_v2": self.set_current_value,
            "ovp": self.ovp_value,
            "ocp": self.ocp_value,
            "_meta": {"set_current_readback_v2": {"status": "ok", "age_s": 0.0}},
        }

    async def set_current(self, value):
        self.set_current_calls.append(float(value))
        self.set_current_value = float(value)
        return True

    async def turn_off(self, entity_id=None):
        self.turn_off_calls += 1
        self.output_on = False
        self.lease.armed = False
        self.lease.remaining_s = 0.0
        return True


class FakeControlMode:
    def __init__(self):
        self.hands_off = True
        self.release_in_progress = False
        self.mode = "hands_off"

    async def return_pb_control(self):
        self.hands_off = False
        self.mode = "pb_managed"
        return True

    async def enter_hands_off(self):
        self.hands_off = True
        self.mode = "hands_off"
        return True


class FakeManual:
    def __init__(self, hass, lease):
        self.hass = hass
        self.lease = lease
        self.is_active = False
        self.request = None
        self.stop_reason = ""

    async def start(self, request):
        self.request = request
        self.hass.set_voltage_value = float(request.voltage_v)
        self.hass.set_current_value = float(request.current_a)
        self.hass.ovp_value = float(request.ovp_v)
        self.hass.ocp_value = float(request.ocp_a)
        self.hass.output_on = True
        self.lease.armed = True
        self.lease.remaining_s = 900.0
        self.lease.generation += 1
        self.is_active = True
        return True

    async def stop(self, reason="operator_stop"):
        self.stop_reason = str(reason)
        confirmed = bool(await self.hass.turn_off())
        if confirmed:
            self.is_active = False
        return confirmed


class FakeControl:
    def __init__(self, app):
        self.app = app
        self._operation_lock = asyncio.Lock()
        self.dispatch = self._fallback

    async def _fallback(self, request):
        return {"ok": False, "error": "unknown operation"}

    async def _raw_live(self):
        return await self.app.hass.get_all_live()

    async def _lease_state(self):
        return self.app.lease

    @staticmethod
    def _is_on(live):
        return live.get("switch") == "on" and float(live.get("output_state_code_v2")) == 1.0

    @staticmethod
    def _is_off(live):
        return live.get("switch") == "off" and float(live.get("output_state_code_v2")) == 0.0

    @staticmethod
    def _require_fields(request, fields):
        if set(request) != fields:
            from physical_test_control import PhysicalTestControlError
            raise PhysicalTestControlError("unexpected or missing request fields")

    @staticmethod
    def _error(message):
        return {"ok": False, "error": str(message)}


class FakeApp:
    def __init__(self, journal):
        self.lease = FakeLease()
        self.hass = FakeHass(self.lease)
        self.rd_control_mode_manager = FakeControlMode()
        self.manual_session_manager = FakeManual(self.hass, self.lease)
        self.charge_controller = SimpleNamespace(is_active=False)
        self.rd_managed_live_adoption = SimpleNamespace(active=False, off_pending=False)
        self.rd_managed_mix_adoption = SimpleNamespace(active=False, off_pending=False)
        self.diagnostic_action_journal = journal


class DiagnosticPhysicalControlTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.journal = DiagnosticActionJournal(os.path.join(self.tmp.name, "diag.json"))
        self.app = FakeApp(self.journal)
        self.control = FakeControl(self.app)
        self.extension = PhysicalTestControlDiagnostic(self.app, self.control)
        self.control.dispatch = self.extension.dispatch
        identity = SimpleNamespace(
            battery_id="battery-a",
            chemistry=BatteryChemistry.AGM,
            nominal_capacity_ah=80.0,
        )
        self.record = SimpleNamespace(identity=identity)

    async def asyncTearDown(self):
        cleanup = self.extension._restart_cleanup_task
        if cleanup is not None and not cleanup.done():
            cleanup.cancel()
            try:
                await cleanup
            except BaseException:
                pass
        self.tmp.cleanup()

    async def test_cancel_after_step_uses_real_probe_cleanup_and_finishes_hands_off(self):
        with patch(
            "physical_test_control_diagnostic.get_battery",
            new=AsyncMock(return_value=self.record),
        ):
            response = await self.control.dispatch(
                {"op": "diagnostic_probe_cancel_after_step", "battery_id": "battery-a"}
            )
        self.assertTrue(response["ok"])
        result = response["result"]
        self.assertTrue(result["cancelled"])
        self.assertTrue(result["original_current_restored_before_off"])
        self.assertEqual(result["output"], "off")
        self.assertFalse(result["lease_armed"])
        self.assertEqual(self.app.rd_control_mode_manager.mode, "hands_off")
        self.assertEqual(self.app.hass.set_current_calls, [0.20, 0.30])
        probes = [r for r in self.journal.records if r.kind is DiagnosticActionKind.PROBE]
        self.assertEqual(len(probes), 1)
        self.assertIs(probes[0].status, DiagnosticActionStatus.FAILED)
        self.assertIn("CancelledError", probes[0].note)

    async def test_prepare_restart_returns_running_journal_then_deadline_cleans_up(self):
        with patch(
            "physical_test_control_diagnostic.get_battery",
            new=AsyncMock(return_value=self.record),
        ), patch("physical_test_control_diagnostic._RESTART_WINDOW_S", 0.05):
            response = await self.control.dispatch(
                {"op": "diagnostic_probe_prepare_restart_window", "battery_id": "battery-a"}
            )
            self.assertTrue(response["ok"])
            result = response["result"]
            self.assertTrue(result["ready_for_sigkill"])
            self.assertEqual(result["journal_status"], "running")
            self.assertEqual(result["set_current"], 0.20)
            self.assertEqual(result["output"], "on")
            self.assertTrue(result["lease_armed"])
            self.assertEqual(len(self.journal.active(kind=DiagnosticActionKind.PROBE)), 1)
            cleanup = self.extension._restart_cleanup_task
            self.assertIsNotNone(cleanup)
            await cleanup
        self.assertFalse(self.app.hass.output_on)
        self.assertFalse(self.app.lease.armed)
        self.assertEqual(self.app.rd_control_mode_manager.mode, "hands_off")
        self.assertEqual(self.app.hass.set_current_calls, [0.20, 0.30])
        self.assertEqual(self.journal.active(kind=DiagnosticActionKind.PROBE), [])

    async def test_probe_infrastructure_failure_after_manual_start_is_cleaned_up(self):
        self.app.diagnostic_action_journal = None
        with patch(
            "physical_test_control_diagnostic.get_battery",
            new=AsyncMock(return_value=self.record),
        ):
            response = await self.control.dispatch(
                {"op": "diagnostic_probe_cancel_after_step", "battery_id": "battery-a"}
            )
        self.assertFalse(response["ok"])
        self.assertFalse(self.app.hass.output_on)
        self.assertFalse(self.app.lease.armed)
        self.assertFalse(self.app.manual_session_manager.is_active)
        self.assertEqual(self.app.rd_control_mode_manager.mode, "hands_off")

    async def test_non_string_battery_id_is_rejected_without_actuation(self):
        response = await self.control.dispatch(
            {"op": "diagnostic_probe_cancel_after_step", "battery_id": 123}
        )
        self.assertFalse(response["ok"])
        self.assertFalse(self.app.hass.output_on)
        self.assertEqual(self.app.rd_control_mode_manager.mode, "hands_off")

    async def test_extra_fields_are_rejected(self):
        response = await self.control.dispatch(
            {
                "op": "diagnostic_probe_prepare_restart_window",
                "battery_id": "battery-a",
                "current": 5.0,
            }
        )
        self.assertFalse(response["ok"])
        self.assertFalse(self.app.hass.output_on)


if __name__ == "__main__":
    unittest.main()
