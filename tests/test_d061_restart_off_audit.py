import json
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import runtime_safety
from manual_mode import ManualSessionState
from rd_control_mode import RdControlMode
from rd_managed_adoption import ManagedAdoptionState, ManagedLiveAdoptionCoordinator
from runtime_safety_v2 import V2RuntimeSafetyGuard


def _stamp(offset_s: float) -> str:
    return (
        datetime(2026, 9, 3, tzinfo=timezone.utc) + timedelta(seconds=offset_s)
    ).isoformat()


def _live(code: int, heartbeat_s: float) -> dict:
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


class _Hass:
    def __init__(self, reports, events):
        self.reports = list(reports)
        self.events = events
        self.read_count = 0
        self.turn_off_calls = 0

    async def get_all_live(self):
        index = min(self.read_count, len(self.reports) - 1)
        self.read_count += 1
        return dict(self.reports[index])

    async def turn_off(self, entity_id=None):
        self.turn_off_calls += 1
        self.events.append("raw-output-off")
        return True

    async def turn_on(self, entity_id=None):
        return True

    async def set_voltage(self, value):
        return True

    async def set_current(self, value):
        return True

    async def set_ovp(self, value):
        return True

    async def set_ocp(self, value):
        return True


class _Lease:
    def __init__(self, events):
        self.events = events
        self.disarm_calls = 0

    async def disarm(self):
        self.disarm_calls += 1
        self.events.append("lease-disarm")
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


class _Manager:
    def __init__(self, guard):
        self.guard = guard
        self.mode = RdControlMode.PB_MANAGED

    @property
    def hands_off(self):
        return self.mode is RdControlMode.HANDS_OFF


class D061RestartOffAuditTests(unittest.IsolatedAsyncioTestCase):
    def _build(self, reports, events):
        hass = _Hass(reports, events)
        lease = _Lease(events)
        manual = _Manual()
        app = types.SimpleNamespace(
            hass=hass,
            edge_safety_lease=lease,
            ENTITY_MAP={"switch": "switch.rd_output"},
            charge_controller=types.SimpleNamespace(is_active=True),
            manual_session_manager=manual,
            _charge_notify=lambda *args, **kwargs: None,
        )
        guard = V2RuntimeSafetyGuard(app)
        guard.install()
        manager = _Manager(guard)
        return app, guard, manager, lease, manual

    async def _run_with_clock(self, operation):
        clock = _Clock()

        async def fake_sleep(delay):
            clock.monotonic += float(delay)

        with patch.object(runtime_safety.time, "monotonic", lambda: clock.monotonic), patch.object(
            runtime_safety.time, "time", lambda: clock.epoch
        ), patch.object(runtime_safety.asyncio, "sleep", fake_sleep):
            return await operation()

    @staticmethod
    def _active_state(path):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "version": 1,
                    "state": "active",
                    "session_id": "session",
                    "battery_id": "battery",
                    "chemistry": "agm",
                    "capacity_ah": 80.0,
                    "max_authority": None,
                    "current_authority": None,
                    "started_at_s": 1.0,
                },
                handle,
            )

    async def test_pb_managed_restart_logs_canonical_off_before_first_lease_disarm(self):
        events = []
        app, guard, manager, lease, manual = self._build(
            [_live(1, 0), _live(0, 1)], events
        )

        def capture_info(message, *args):
            rendered = message % args if args else str(message)
            events.append(f"log:{rendered}")

        with tempfile.TemporaryDirectory() as tmp:
            state_file = f"{tmp}/state.json"
            self._active_state(state_file)
            coordinator = ManagedLiveAdoptionCoordinator(
                app,
                manager,
                state_file=state_file,
                edge=object(),
            )
            self.assertEqual(coordinator.state, ManagedAdoptionState.OFF_PENDING)
            with patch.object(runtime_safety.logger, "info", side_effect=capture_info):
                self.assertTrue(
                    await self._run_with_clock(coordinator.recover_startup),
                    coordinator.last_status,
                )

        canonical = next(
            index
            for index, event in enumerate(events)
            if event.startswith(
                "log:Output OFF confirmed: source=output_state_code_v2"
            )
        )
        disarm_allowed = next(
            index
            for index, event in enumerate(events)
            if event == "log:Output OFF verified; edge lease disarm may proceed"
        )
        first_disarm = events.index("lease-disarm")

        self.assertLess(canonical, disarm_allowed)
        self.assertLess(disarm_allowed, first_disarm)
        self.assertGreaterEqual(lease.disarm_calls, 1)
        self.assertEqual(coordinator.state, ManagedAdoptionState.INTERRUPTED)
        self.assertFalse(manual.is_active)

    async def test_pb_managed_restart_never_disarms_when_canonical_off_is_unconfirmed(self):
        events = []
        app, guard, manager, lease, manual = self._build(
            [_live(1, 0), _live(1, 1)], events
        )
        guard.OFF_CONFIRMATION_WINDOW_S = 0.0

        def capture_info(message, *args):
            rendered = message % args if args else str(message)
            events.append(f"log:{rendered}")

        with tempfile.TemporaryDirectory() as tmp:
            state_file = f"{tmp}/state.json"
            self._active_state(state_file)
            coordinator = ManagedLiveAdoptionCoordinator(
                app,
                manager,
                state_file=state_file,
                edge=object(),
            )
            with patch.object(runtime_safety.logger, "info", side_effect=capture_info):
                self.assertFalse(
                    await self._run_with_clock(coordinator.recover_startup)
                )

        self.assertEqual(lease.disarm_calls, 0)
        self.assertNotIn("lease-disarm", events)
        self.assertNotIn(
            "log:Output OFF verified; edge lease disarm may proceed",
            events,
        )
        self.assertEqual(coordinator.state, ManagedAdoptionState.OFF_PENDING)
        self.assertTrue(manual.is_active)


if __name__ == "__main__":
    unittest.main()
