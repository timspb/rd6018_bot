import types
import unittest

from edge_safety_lease import EdgeSafetyLeaseConfig
from rd_autonomous_mode import (
    RdAutonomousModeCoordinator,
    install_rd_autonomous_mode,
)
from runtime_safety import RuntimeSafetyError


class DummyLease:
    def __init__(self):
        self.config = EdgeSafetyLeaseConfig()


class DummyGuard:
    def __init__(self):
        self.edge_lease_enforced = True
        self.edge_safety_lease = DummyLease()
        self._off_unconfirmed = False
        self._orphan_output_seen_at = 123.0
        self.live = {"switch": "off", "autonomous_mode": "off"}

    async def _raw_live(self):
        return dict(self.live)


class DummyManager:
    def __init__(self):
        self.guard = DummyGuard()
        self.mode = types.SimpleNamespace()
        self.hands_off = False
        self.pb_managed = True
        self._edge_autonomous = False
        self.enter_calls = 0
        self.return_calls = 0
        self.sessions = False
        self.writes = []
        self.clear_calls = 0

    @property
    def edge_autonomous(self):
        return bool(self._edge_autonomous)

    def _managed_session_active(self):
        return self.sessions

    def _observe_edge_mode(self, live):
        raw = live.get("autonomous_mode")
        if raw in (True, "on", "true", "1", 1):
            self._edge_autonomous = True
        elif raw in (False, "off", "false", "0", 0):
            self._edge_autonomous = False

    async def enter_hands_off(self):
        self.enter_calls += 1
        self.hands_off = True
        self.pb_managed = False
        return True

    async def return_pb_control(self):
        self.return_calls += 1
        self.hands_off = False
        self.pb_managed = True
        return True

    def _write_mode(self, mode):
        self.writes.append(mode)

    def _clear_stale_auto_restore_authority(self):
        self.clear_calls += 1


class FakeEdge:
    def __init__(self):
        self.autonomous = False
        self.enter_calls = 0
        self.exit_calls = 0
        self.fail_enter = False
        self.fail_exit = False

    async def read_autonomous(self):
        return self.autonomous

    async def enter(self):
        self.enter_calls += 1
        if self.fail_enter:
            raise RuntimeError("edge enter failed")
        self.autonomous = True
        return object()

    async def exit(self):
        self.exit_calls += 1
        if self.fail_exit:
            raise RuntimeError("edge exit failed")
        self.autonomous = False
        return object()


class RdAutonomousModeTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def make():
        manager = DummyManager()
        coordinator = RdAutonomousModeCoordinator(types.SimpleNamespace(), manager)
        coordinator.edge = FakeEdge()
        return manager, coordinator

    async def test_enter_crosses_hands_off_before_edge_autonomous(self):
        manager, coordinator = self.make()
        self.assertTrue(await coordinator.enter())
        self.assertEqual(manager.enter_calls, 1)
        self.assertTrue(manager.hands_off)
        self.assertFalse(manager.pb_managed)
        self.assertTrue(manager._edge_autonomous)
        self.assertEqual(coordinator.edge.enter_calls, 1)
        self.assertIsNone(manager.guard._orphan_output_seen_at)

    async def test_entry_requires_confirmed_output_off(self):
        manager, coordinator = self.make()
        manager.guard.live["switch"] = "on"
        with self.assertRaisesRegex(RuntimeSafetyError, "confirmed Output OFF"):
            await coordinator.enter()
        self.assertEqual(manager.enter_calls, 0)
        self.assertEqual(coordinator.edge.enter_calls, 0)

    async def test_entry_rejects_stale_output_off_evidence(self):
        manager, coordinator = self.make()
        manager.guard.live["_meta"] = {
            "switch": {"status": "unavailable"},
        }
        with self.assertRaisesRegex(RuntimeSafetyError, "fresh confirmed Output OFF"):
            await coordinator.enter()
        self.assertEqual(manager.enter_calls, 0)
        self.assertEqual(coordinator.edge.enter_calls, 0)

    async def test_ambiguous_edge_entry_never_rolls_back_bot_authority(self):
        manager, coordinator = self.make()
        coordinator.edge.fail_enter = True
        with self.assertRaisesRegex(RuntimeSafetyError, "RD remains HANDS_OFF"):
            await coordinator.enter()
        self.assertTrue(manager.hands_off)
        self.assertFalse(manager.pb_managed)
        self.assertEqual(manager.return_calls, 0)
        self.assertFalse(manager._edge_autonomous)

    async def test_exit_is_off_only_and_returns_managed_idle_after_edge_ack(self):
        manager, coordinator = self.make()
        manager.hands_off = True
        manager.pb_managed = False
        manager._edge_autonomous = True
        manager.guard.live["autonomous_mode"] = "on"
        coordinator.edge.autonomous = True
        self.assertTrue(await coordinator.exit())
        self.assertEqual(coordinator.edge.exit_calls, 1)
        self.assertEqual(manager.return_calls, 1)
        self.assertFalse(manager._edge_autonomous)
        self.assertTrue(manager.pb_managed)

    async def test_failed_exit_keeps_autonomous_authority(self):
        manager, coordinator = self.make()
        manager.hands_off = True
        manager.pb_managed = False
        manager._edge_autonomous = True
        manager.guard.live["autonomous_mode"] = "on"
        coordinator.edge.autonomous = True
        coordinator.edge.fail_exit = True
        with self.assertRaisesRegex(RuntimeSafetyError, "not positively acknowledged"):
            await coordinator.exit()
        self.assertTrue(manager._edge_autonomous)
        self.assertTrue(manager.hands_off)
        self.assertEqual(manager.return_calls, 0)

    async def test_active_managed_session_blocks_autonomous_entry(self):
        manager, coordinator = self.make()
        manager.sessions = True
        with self.assertRaisesRegex(RuntimeSafetyError, "active managed session"):
            await coordinator.enter()
        self.assertEqual(manager.enter_calls, 0)

    async def test_stale_generic_pb_restore_cannot_bypass_edge_autonomous(self):
        manager = DummyManager()
        app = types.SimpleNamespace()
        install_rd_autonomous_mode(app, manager, install_ui=False)
        manager.hands_off = True
        manager.pb_managed = False
        manager._edge_autonomous = True

        with self.assertRaisesRegex(RuntimeSafetyError, "explicit AUTONOMOUS exit"):
            await manager.return_pb_control()

        self.assertEqual(manager.return_calls, 0)
        self.assertTrue(manager.hands_off)


if __name__ == "__main__":
    unittest.main()
