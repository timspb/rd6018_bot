import asyncio
import json
import inspect
import os
import socket
import tempfile
import unittest
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from battery_registry import BatteryRecord
from pb_domain import BatteryChemistry, BatteryCondition, BatteryIdentity, BatteryLifecycle
from physical_test_control import (
    ENV_ENABLE,
    PhysicalTestControl,
    _OPS,
)
from tools.physical_test_control_client import request as client_request


class Mode(str, Enum):
    HANDS_OFF = "hands_off"
    PB_MANAGED = "pb_managed"


class ManualState(str, Enum):
    STOPPED = "stopped"
    ACTIVE = "active"


class AdoptionState(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    FAILED = "failed"


class FakeLease:
    def __init__(self):
        self.config = SimpleNamespace(lease_ttl_s=900.0)
        self.state = SimpleNamespace(
            armed=False,
            tripped=False,
            boot_quarantine=False,
            generation=4,
            remaining_s=0.0,
            modbus_age_s=2.0,
        )

    async def read_state(self):
        return self.state


class FakeGuard:
    def __init__(self, live):
        self.live = live
        self.edge_safety_lease = FakeLease()

    async def _raw_live(self):
        return dict(self.live)


class FakeManager:
    def __init__(self, mode=Mode.HANDS_OFF):
        self.mode = mode
        self.enter_calls = 0

    @property
    def hands_off(self):
        return self.mode is Mode.HANDS_OFF

    async def enter_hands_off(self):
        self.enter_calls += 1
        self.mode = Mode.HANDS_OFF
        return True


class FakeAdoption:
    def __init__(self, app=None):
        self.app = app
        self.state = AdoptionState.IDLE
        self.max_authority = None
        self.current_authority = None
        self.adopt_calls = []
        self.stop_calls = 0
        self.recover_calls = 0

    @property
    def active(self):
        return self.state is AdoptionState.ACTIVE

    @property
    def off_pending(self):
        return False

    @staticmethod
    def fingerprint_from_live(live):
        return SimpleNamespace(
            set_voltage_v=float(live["set_voltage"]),
            set_current_a=float(live["set_current"]),
            ovp_v=float(live["ovp"]),
            ocp_a=float(live["ocp"]),
        )

    async def adopt(self, preview):
        self.adopt_calls.append(preview)
        self.state = AdoptionState.ACTIVE
        self.max_authority = preview.fingerprint
        self.current_authority = preview.fingerprint
        return True

    async def verified_stop(self):
        self.stop_calls += 1
        self.state = AdoptionState.FAILED
        if self.app is not None:
            self.app.runtime_safety_guard.live["switch"] = "off"
            self.app.runtime_safety_guard.live["output_state_code_v2"] = 0.0
        return True

    async def recover_startup(self):
        self.recover_calls += 1
        return True


class FakeApp:
    def __init__(self, *, mode=Mode.HANDS_OFF, output="off"):
        live = {
            "switch": output,
            "output_state_code_v2": 0.0 if output == "off" else 1.0,
            "voltage": 0.0 if output == "off" else 13.0,
            "current": 0.0 if output == "off" else 0.19,
            "set_voltage": 13.6,
            "set_current": 0.2,
            "ovp": 13.8,
            "ocp": 0.4,
            "protection_code": 0.0,
            "protection_status": "normal",
            "_meta": {"switch": {"age_s": 2.0, "source_key": "output_state_code_v2"}, "protection_code": {"age_s": 2.0}},
        }
        self.runtime_safety_guard = FakeGuard(live)
        self.rd_control_mode_manager = FakeManager(mode)
        self.rd_managed_live_adoption = FakeAdoption(self)
        self.manual_session_manager = SimpleNamespace(state=ManualState.STOPPED)
        self.rd_managed_mix_adoption = SimpleNamespace(active=False, off_pending=False)


def battery_record(chemistry=BatteryChemistry.AGM):
    return BatteryRecord(
        identity=BatteryIdentity(
            battery_id="varta_agm80_a0019828108",
            chemistry=chemistry,
            nominal_capacity_ah=80.0,
            manufacturer="Varta",
            model="Mercedes A 001 982 81 08",
        ),
        lifecycle=BatteryLifecycle(condition=BatteryCondition.UNKNOWN, cca_a=800.0),
    )


class PhysicalTestControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            control = PhysicalTestControl(FakeApp(), socket_path="/tmp/rd6018-test-disabled.sock")
        self.assertFalse(control.enabled)
        self.assertFalse(await control.start())
        self.assertIsNone(control._server)

    @unittest.skipUnless(hasattr(socket, "AF_UNIX"), "Unix sockets unavailable")
    async def test_binds_unix_socket_and_never_tcp(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "control.sock")
            control = PhysicalTestControl(FakeApp(), socket_path=path, enabled=True)
            with patch("physical_test_control.asyncio.start_server", side_effect=AssertionError("TCP forbidden")):
                self.assertTrue(await control.start())
            self.assertEqual(stat_mode(path), 0o600)
            await control.stop()
            self.assertFalse(os.path.exists(path))

    async def test_separate_client_is_transport_only_and_cannot_resume_or_mutate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "control.sock")
            app = FakeApp()
            control = PhysicalTestControl(app, socket_path=path, enabled=True)
            await control.start()
            try:
                response = await asyncio.to_thread(client_request, path, {"op": "status"})
                self.assertTrue(response["ok"])
                self.assertEqual(app.rd_control_mode_manager.enter_calls, 0)
                self.assertEqual(app.rd_managed_live_adoption.adopt_calls, [])
                self.assertEqual(app.rd_managed_live_adoption.recover_calls, 0)
            finally:
                await control.stop()

        client_source = inspect.getsource(client_request)
        self.assertNotIn("RdControlModeManager", client_source)
        self.assertNotIn("ManagedLiveAdoptionCoordinator", client_source)

    async def test_malformed_unknown_and_extra_fields_fail_closed(self):
        control = PhysicalTestControl(FakeApp(), enabled=True)
        for request in (None, [], {"op": "unknown"}, {"op": "status", "extra": 1}):
            response = await control.dispatch(request)
            self.assertFalse(response["ok"])
        self.assertEqual(control.app.rd_control_mode_manager.enter_calls, 0)

    async def test_hands_off_requires_verified_off(self):
        app = FakeApp(mode=Mode.PB_MANAGED, output="on")
        control = PhysicalTestControl(app, enabled=True)
        response = await control.dispatch({"op": "enter_hands_off_verified_off"})
        self.assertFalse(response["ok"])
        self.assertEqual(app.rd_control_mode_manager.enter_calls, 0)

    async def test_enter_hands_off_delegates_in_process_manager(self):
        app = FakeApp(mode=Mode.PB_MANAGED, output="off")
        control = PhysicalTestControl(app, enabled=True)
        response = await control.dispatch({"op": "enter_hands_off_verified_off"})
        self.assertTrue(response["ok"])
        self.assertEqual(app.rd_control_mode_manager.enter_calls, 1)

    async def test_adopt_uses_existing_coordinator_and_registry_identity_only(self):
        app = FakeApp(mode=Mode.HANDS_OFF, output="on")
        control = PhysicalTestControl(app, enabled=True)
        with patch("physical_test_control.get_battery", new=AsyncMock(return_value=battery_record())):
            response = await control.dispatch({"op": "d061_adopt_battery", "battery_id": "varta_agm80_a0019828108"})
        self.assertTrue(response["ok"])
        self.assertEqual(len(app.rd_managed_live_adoption.adopt_calls), 1)
        preview = app.rd_managed_live_adoption.adopt_calls[0]
        self.assertEqual(preview.battery_id, "varta_agm80_a0019828108")
        self.assertEqual(preview.capacity_ah, 80.0)

    async def test_adopt_rejects_custom_and_does_not_accept_arbitrary_parameters(self):
        app = FakeApp(mode=Mode.HANDS_OFF, output="on")
        control = PhysicalTestControl(app, enabled=True)
        with patch("physical_test_control.get_battery", new=AsyncMock(return_value=battery_record(BatteryChemistry.CUSTOM))):
            response = await control.dispatch({"op": "d061_adopt_battery", "battery_id": "varta_agm80_a0019828108"})
        self.assertFalse(response["ok"])
        response = await control.dispatch({"op": "d061_adopt_battery", "battery_id": "varta_agm80_a0019828108", "set_current": 9.0})
        self.assertFalse(response["ok"])
        self.assertEqual(app.rd_managed_live_adoption.adopt_calls, [])

    async def test_adoption_cannot_bypass_existing_preflight(self):
        app = FakeApp(mode=Mode.PB_MANAGED, output="on")
        control = PhysicalTestControl(app, enabled=True)
        with patch("physical_test_control.get_battery", new=AsyncMock(return_value=battery_record())):
            response = await control.dispatch({"op": "d061_adopt_battery", "battery_id": "varta_agm80_a0019828108"})
        self.assertFalse(response["ok"])
        self.assertEqual(app.rd_managed_live_adoption.adopt_calls, [])

    async def test_verified_stop_requires_active_adopted_manual_and_is_not_toggle(self):
        app = FakeApp(mode=Mode.PB_MANAGED, output="on")
        control = PhysicalTestControl(app, enabled=True)
        response = await control.dispatch({"op": "d061_verified_stop"})
        self.assertFalse(response["ok"])
        app.rd_managed_live_adoption.state = AdoptionState.ACTIVE
        response = await control.dispatch({"op": "d061_verified_stop"})
        self.assertTrue(response["ok"])
        self.assertEqual(app.rd_managed_live_adoption.stop_calls, 1)

    async def test_status_is_read_only_in_process_snapshot(self):
        app = FakeApp()
        control = PhysicalTestControl(app, enabled=True)
        response = await control.dispatch({"op": "status"})
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["rd_control_mode"], "hands_off")
        self.assertEqual(response["result"]["edge_lease"]["ttl_s"], 900.0)
        self.assertEqual(app.rd_control_mode_manager.enter_calls, 0)

    def test_operation_surface_contains_no_widening_operation(self):
        self.assertEqual(
            _OPS,
            {"status", "enter_hands_off_verified_off", "d061_adopt_battery", "d061_verified_stop"},
        )


def stat_mode(path):
    return os.stat(path).st_mode & 0o777
