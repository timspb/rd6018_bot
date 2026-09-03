import asyncio
import json
import types
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import runtime_safety
from manual_mode import ManualSessionState
from rd_control_mode import RdControlMode
from rd_managed_adoption import ManagedAdoptionState, ManagedLiveAdoptionCoordinator
from runtime_safety import OutputOffNotConfirmed
from runtime_safety_v2 import V2RuntimeSafetyGuard


def _stamp(offset_s: float) -> str:
    return (datetime(2026, 9, 3, tzinfo=timezone.utc) + timedelta(seconds=offset_s)).isoformat()


def _v2_live(code: int, heartbeat_s: float) -> dict:
    stamp = _stamp(heartbeat_s)
    return {
        "switch": "on" if code else "off",
        "output_state_code_v2": code,
        "_meta": {
            "output_state_code_v2": {
                "status": "ok",
                "last_reported": stamp,
                "last_updated": stamp,
            },
            "switch": {
                "status": "ok",
                "source_key": "output_state_code_v2",
                "last_reported": stamp,
                "last_updated": stamp,
            },
        },
    }


class _Clock:
    def __init__(self) -> None:
        self.monotonic = 100.0
        self.epoch = datetime(2026, 9, 3, tzinfo=timezone.utc).timestamp()


class _SequencedHass:
    def __init__(self, reports, *, off_result=True, read_errors=0):
        self.reports = list(reports)
        self.off_result = off_result
        self.read_errors = int(read_errors)
        self.read_count = 0
        self.turn_off_calls = 0
        self.actuator_writes = []

    async def get_all_live(self):
        if self.read_errors:
            self.read_errors -= 1
            raise RuntimeError("synthetic HA read failure")
        index = min(self.read_count, len(self.reports) - 1)
        self.read_count += 1
        return dict(self.reports[index])

    async def turn_on(self, entity_id=None):
        return True

    async def set_voltage(self, value):
        self.actuator_writes.append(("voltage", value))
        return True

    async def set_current(self, value):
        self.actuator_writes.append(("current", value))
        return True

    async def set_ovp(self, value):
        self.actuator_writes.append(("ovp", value))
        return True

    async def set_ocp(self, value):
        self.actuator_writes.append(("ocp", value))
        return True

    async def turn_off(self, entity_id=None):
        self.turn_off_calls += 1
        return bool(self.off_result)


class _Lease:
    def __init__(self):
        self.disarm_calls = 0

    async def disarm(self):
        self.disarm_calls += 1
        return True


class _Manual:
    def __init__(self):
        self.state = ManualSessionState.ACTIVE
        self.stop_reason = ""
        self.cooling_started_at = None
        self._task = None

    @property
    def is_active(self):
        return self.state in {
            ManualSessionState.ARMING,
            ManualSessionState.ACTIVE,
            ManualSessionState.COOLING,
        }

    def _persist(self):
        pass


class _RecoveryManager:
    def __init__(self, app, guard):
        self.app = app
        self.guard = guard
        self.mode = RdControlMode.HANDS_OFF

    @property
    def hands_off(self):
        return self.mode is RdControlMode.HANDS_OFF

    async def operator_output_off(self, entity_id=None):
        return await self.guard._ensure_output_off("D061 test recovery", entity_id)


class VerifiedOffContractTests(unittest.IsolatedAsyncioTestCase):
    def _guard(self, reports, *, lease=None, off_result=True, read_errors=0):
        hass = _SequencedHass(reports, off_result=off_result, read_errors=read_errors)
        app = types.SimpleNamespace(
            hass=hass,
            ENTITY_MAP={"switch": "switch.rd_output"},
            charge_controller=types.SimpleNamespace(is_active=True),
            manual_session_manager=None,
            _charge_notify=lambda *args, **kwargs: None,
        )
        if lease is not None:
            app.edge_safety_lease = lease
        guard = V2RuntimeSafetyGuard(app)
        guard.edge_lease_enforced = bool(lease)
        return app, guard

    async def _run_with_fake_clock(self, guard, operation):
        clock = _Clock()

        async def fake_sleep(delay):
            clock.monotonic += float(delay)

        with patch.object(runtime_safety.time, "monotonic", lambda: clock.monotonic), patch.object(
            runtime_safety.time, "time", lambda: clock.epoch
        ), patch.object(runtime_safety.asyncio, "sleep", fake_sleep):
            return await operation()

    async def test_delayed_physical_off_waits_for_register_18_heartbeat(self):
        app, guard = self._guard([_v2_live(1, 0), _v2_live(1, 5), _v2_live(0, 10)])
        guard.OFF_CONFIRMATION_POLL_S = 5.0
        self.assertTrue(await self._run_with_fake_clock(guard, guard.turn_off))
        self.assertEqual(app.hass.turn_off_calls, 2)
        self.assertFalse(guard._off_unconfirmed)

    async def test_second_poll_boundary_is_inside_bounded_window(self):
        app, guard = self._guard([_v2_live(1, 0), _v2_live(1, 5), _v2_live(0, 10)])
        guard.OFF_CONFIRMATION_POLL_S = 5.0
        self.assertTrue(await self._run_with_fake_clock(guard, guard.turn_off))
        self.assertEqual(app.hass.turn_off_calls, 2)

    async def test_never_off_retries_once_and_keeps_unconfirmed(self):
        app, guard = self._guard(
            [_v2_live(1, 0), _v2_live(1, 5), _v2_live(1, 10), _v2_live(1, 15)]
        )
        guard.OFF_CONFIRMATION_POLL_S = 5.0
        with self.assertRaises(OutputOffNotConfirmed):
            await self._run_with_fake_clock(guard, guard.turn_off)
        self.assertEqual(app.hass.turn_off_calls, 2)
        self.assertTrue(guard._off_unconfirmed)

    async def test_off_retry_path_never_writes_setpoints_or_protection(self):
        app, guard = self._guard([_v2_live(1, 0), _v2_live(1, 5), _v2_live(1, 10)])
        guard.OFF_CONFIRMATION_POLL_S = 5.0
        with self.assertRaises(OutputOffNotConfirmed):
            await self._run_with_fake_clock(guard, guard.turn_off)
        self.assertEqual(app.hass.actuator_writes, [])

    async def test_stale_cached_off_is_not_confirmation(self):
        stale = _v2_live(0, 0)
        app, guard = self._guard([stale, stale, stale, stale])
        guard.OFF_CONFIRMATION_POLL_S = 5.0
        with self.assertRaises(OutputOffNotConfirmed):
            await self._run_with_fake_clock(guard, guard.turn_off)
        self.assertEqual(app.hass.turn_off_calls, 1)
        self.assertTrue(guard._off_unconfirmed)

    async def test_fresh_post_command_off_confirms_immediately(self):
        app, guard = self._guard([_v2_live(1, 0), _v2_live(0, 1)])
        self.assertTrue(await self._run_with_fake_clock(guard, guard.turn_off))
        self.assertEqual(app.hass.turn_off_calls, 1)

    async def test_readback_failure_fails_closed(self):
        app, guard = self._guard([_v2_live(1, 0)], read_errors=10)
        guard.OFF_CONFIRMATION_WINDOW_S = 0.0
        with self.assertRaises(OutputOffNotConfirmed):
            await self._run_with_fake_clock(guard, guard.turn_off)
        self.assertTrue(guard._off_unconfirmed)

    async def test_lease_disarms_only_after_confirmed_off(self):
        lease = _Lease()
        app, guard = self._guard([_v2_live(1, 0), _v2_live(0, 1)], lease=lease)
        self.assertTrue(await self._run_with_fake_clock(guard, guard.turn_off))
        self.assertEqual(lease.disarm_calls, 1)

        lease = _Lease()
        app, guard = self._guard([_v2_live(1, 0), _v2_live(1, 1)], lease=lease)
        guard.OFF_CONFIRMATION_WINDOW_S = 0.0
        with self.assertRaises(OutputOffNotConfirmed):
            await self._run_with_fake_clock(guard, guard.turn_off)
        self.assertEqual(lease.disarm_calls, 0)

    async def test_d061_restart_recovery_delayed_off_becomes_interrupted(self):
        with self.subTest("delayed-off"):
            with self._state_file() as state_file:
                reports = [_v2_live(1, 0), _v2_live(1, 5), _v2_live(0, 10)]
                app, guard = self._guard(reports)
                app.manual_session_manager = _Manual()
                manager = _RecoveryManager(app, guard)
                payload = {
                    "version": 1,
                    "state": "active",
                    "session_id": "session",
                    "battery_id": "battery",
                    "chemistry": "agm",
                    "capacity_ah": 80.0,
                    "max_authority": None,
                    "current_authority": None,
                    "started_at_s": 1.0,
                }
                with open(state_file, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle)
                coordinator = ManagedLiveAdoptionCoordinator(app, manager, state_file=state_file)
                guard.OFF_CONFIRMATION_POLL_S = 5.0
                self.assertEqual(coordinator.state, ManagedAdoptionState.OFF_PENDING)
                self.assertTrue(
                    await self._run_with_fake_clock(guard, coordinator.recover_startup),
                    coordinator.last_status,
                )
                self.assertEqual(coordinator.state, ManagedAdoptionState.INTERRUPTED)
                self.assertFalse(app.manual_session_manager.is_active)

    async def test_d061_restart_recovery_permanent_on_keeps_containment_and_lease(self):
        with self._state_file() as state_file:
            lease = _Lease()
            reports = [_v2_live(1, 0), _v2_live(1, 5), _v2_live(1, 10)]
            app, guard = self._guard(reports, lease=lease)
            app.manual_session_manager = _Manual()
            manager = _RecoveryManager(app, guard)
            with open(state_file, "w", encoding="utf-8") as handle:
                json.dump({"version": 1, "state": "active"}, handle)
            coordinator = ManagedLiveAdoptionCoordinator(
                app, manager, state_file=state_file, edge=object()
            )
            guard.OFF_CONFIRMATION_POLL_S = 5.0
            self.assertFalse(await self._run_with_fake_clock(guard, coordinator.recover_startup))
            self.assertEqual(coordinator.state, ManagedAdoptionState.OFF_PENDING)
            self.assertTrue(guard._off_unconfirmed, coordinator.last_status)
            self.assertEqual(lease.disarm_calls, 0)
            self.assertTrue(app.manual_session_manager.is_active)

    @staticmethod
    @contextmanager
    def _state_file():
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            yield f"{tmp}/state.json"


if __name__ == "__main__":
    unittest.main()
