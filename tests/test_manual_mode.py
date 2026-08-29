import asyncio
import json
import os
import tempfile
import time
import unittest
from types import SimpleNamespace

from manual_mode import (
    ManualChargeRequest,
    ManualSessionManager,
    ManualSessionState,
    ManualStopConditions,
)


class FakeHass:
    def __init__(self):
        self.live = {
            "battery_voltage": 13.0,
            "current": 1.0,
            "temp_ext": 25.0,
            "temp_int": 30.0,
            "input_voltage": 55.0,
            "switch": "off",
            "is_cv": True,
            "is_cc": False,
            "ovp_triggered": False,
            "ocp_triggered": False,
        }
        self.enable_requests = []
        self.off_calls = 0

    async def safe_enable_output(self, **kwargs):
        self.enable_requests.append(dict(kwargs))
        self.live["switch"] = "on"
        return SimpleNamespace(enabled=True, detail="")

    async def turn_off(self, entity_id=None):
        self.off_calls += 1
        self.live["switch"] = "off"
        return True

    async def get_all_live(self):
        return dict(self.live)


class DummyController:
    is_active = False


class ManualModeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.session_file = os.path.join(self.tempdir.name, "manual.json")
        self.hass = FakeHass()
        self.app = SimpleNamespace(hass=self.hass, charge_controller=DummyController())

    def tearDown(self):
        self.tempdir.cleanup()

    def test_exact_17_5v_is_accepted_and_protections_are_derived(self):
        request = ManualChargeRequest(voltage_v=17.5, current_a=12.0)
        self.assertAlmostEqual(request.ovp_v, 17.6)
        self.assertAlmostEqual(request.ocp_a, 12.1)
        with self.assertRaises(ValueError):
            ManualChargeRequest(voltage_v=17.5001, current_a=1.0)

    async def test_start_uses_safe_transaction_and_not_chemistry_controller(self):
        request = ManualChargeRequest(
            voltage_v=14.8,
            current_a=5.0,
            stop=ManualStopConditions(max_active_seconds=3600.0),
        )
        manager = ManualSessionManager(self.app, session_file=self.session_file)
        self.app.manual_session_manager = manager
        self.assertTrue(await manager.start(request))
        self.assertEqual(manager.state, ManualSessionState.ACTIVE)
        self.assertFalse(self.app.charge_controller.is_active)
        self.assertEqual(len(self.hass.enable_requests), 1)
        programmed = self.hass.enable_requests[0]
        self.assertAlmostEqual(programmed["voltage_v"], 14.8)
        self.assertAlmostEqual(programmed["ovp_v"], 14.9)
        self.assertAlmostEqual(programmed["ocp_a"], 5.1)
        assert manager._task is not None
        manager._task.cancel()
        try:
            await manager._task
        except asyncio.CancelledError:
            pass

    async def test_cooling_is_pause_and_resumes_same_manual_setpoints(self):
        request = ManualChargeRequest(voltage_v=15.5, current_a=2.0)
        manager = ManualSessionManager(self.app, session_file=self.session_file)
        self.app.manual_session_manager = manager
        manager.request = request
        manager.state = ManualSessionState.ACTIVE
        manager.started_at = time.time() - 100.0

        self.hass.live["switch"] = "on"
        self.hass.live["temp_ext"] = 40.0
        await manager.observe_once()
        self.assertEqual(manager.state, ManualSessionState.COOLING)
        self.assertEqual(self.hass.live["switch"], "off")

        self.hass.live["temp_ext"] = 35.0
        await manager.observe_once()
        self.assertEqual(manager.state, ManualSessionState.ACTIVE)
        self.assertEqual(self.hass.live["switch"], "on")
        self.assertAlmostEqual(self.hass.enable_requests[-1]["voltage_v"], 15.5)
        self.assertAlmostEqual(self.hass.enable_requests[-1]["current_a"], 2.0)

    async def test_user_time_limit_stops_manual_session(self):
        request = ManualChargeRequest(
            voltage_v=14.5,
            current_a=2.0,
            stop=ManualStopConditions(max_active_seconds=1.0),
        )
        manager = ManualSessionManager(self.app, session_file=self.session_file)
        self.app.manual_session_manager = manager
        manager.request = request
        manager.state = ManualSessionState.ACTIVE
        manager.started_at = time.time() - 10.0
        self.hass.live["switch"] = "on"
        await manager.observe_once()
        self.assertEqual(manager.state, ManualSessionState.STOPPED)
        self.assertEqual(manager.stop_reason, "manual_time_limit")
        self.assertGreaterEqual(self.hass.off_calls, 1)

    def test_active_persisted_manual_never_auto_resumes_after_restart(self):
        with open(self.session_file, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "version": 2,
                    "state": "active",
                    "request": {
                        "voltage_v": 14.8,
                        "current_a": 4.0,
                        "stop": {"max_active_seconds": 3600.0},
                        "battery_id": "",
                        "capacity_ah": 70.0,
                        "notes": "",
                    },
                    "started_at": 123.0,
                    "paused_total_s": 0.0,
                },
                handle,
            )
        manager = ManualSessionManager(self.app, session_file=self.session_file)
        self.assertEqual(manager.state, ManualSessionState.INTERRUPTED)
        self.assertFalse(manager.is_active)
        self.assertEqual(
            manager.stop_reason,
            "process_restart_requires_operator_reauthorization",
        )


if __name__ == "__main__":
    unittest.main()
