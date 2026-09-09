import asyncio
import json
import os
import tempfile
import types
import unittest

from rd_adopted_hands_off_release import install_adopted_hands_off_release_retirement
from rd_control_mode import RdControlMode
from rd_managed_adoption import ManagedAdoptionState
from runtime_safety import RuntimeSafetyError


class FakeCoordinator:
    def __init__(self, state_file, *, state=ManagedAdoptionState.ACTIVE, session_id="d061-a"):
        self.state_file = state_file
        self.state = state
        self.session_id = session_id
        self.last_status = ""
        self._task = None
        self.verified_off_calls = 0
        self.persist_calls = 0

    @property
    def active(self):
        return self.state is ManagedAdoptionState.ACTIVE

    @property
    def off_pending(self):
        return self.state is ManagedAdoptionState.OFF_PENDING

    def _persist(self):
        self.persist_calls += 1
        with open(self.state_file, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "state": self.state.value,
                    "session_id": self.session_id,
                    "last_status": self.last_status,
                },
                handle,
            )

    async def _verified_off(self, reason):
        self.verified_off_calls += 1
        self.state = ManagedAdoptionState.OFF_PENDING
        self.last_status = str(reason)
        self._persist()
        return True


class FakeManager:
    def __init__(self, coordinator, *, mode=RdControlMode.PB_MANAGED, behavior="success"):
        self.mode = mode
        self.behavior = behavior
        self.release_in_progress = False
        self._d061_hands_off_release_retirement_installed = False
        self.coordinator = coordinator
        self.release_verified_off_result = None

    @property
    def hands_off(self):
        return self.mode is RdControlMode.HANDS_OFF

    @property
    def pb_managed(self):
        return self.mode is RdControlMode.PB_MANAGED

    async def enter_hands_off(self):
        self.release_in_progress = True
        if self.behavior == "precommit-fail":
            self.release_in_progress = False
            raise RuntimeSafetyError("precommit failed")

        self.mode = RdControlMode.HANDS_OFF
        # Model the D061 monitor waking after durable HANDS_OFF commit but before the
        # ordinary release helper has returned/retired software state.
        self.release_verified_off_result = await self.coordinator._verified_off(
            "adopted_live_lost_pb_managed_mode"
        )
        self.release_in_progress = False
        if self.behavior == "postcommit-warning":
            raise RuntimeSafetyError("edge ACK lost after durable HANDS_OFF")
        return True


class D061HandsOffReleaseRetirementTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _intent(path, session_id):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "version": 1,
                    "session_id": session_id,
                    "phase": "release_requested",
                    "saved_at_s": 1.0,
                },
                handle,
            )

    async def test_committed_hands_off_suppresses_d061_off_and_retires_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = f"{tmp}/d061.json"
            intent_file = f"{tmp}/release.json"
            coordinator = FakeCoordinator(state_file)
            manager = FakeManager(coordinator)
            app = types.SimpleNamespace(rd_managed_live_adoption=coordinator)

            install_adopted_hands_off_release_retirement(
                app, manager, intent_file=intent_file
            )
            self.assertTrue(await manager.enter_hands_off())

            self.assertTrue(manager.hands_off)
            self.assertFalse(coordinator.active)
            self.assertEqual(coordinator.state, ManagedAdoptionState.INTERRUPTED)
            self.assertEqual(coordinator.verified_off_calls, 0)
            self.assertFalse(manager.release_verified_off_result)
            self.assertFalse(os.path.exists(intent_file))
            self.assertIn("without Output change", coordinator.last_status)

    async def test_postcommit_edge_warning_still_retires_d061_without_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            coordinator = FakeCoordinator(f"{tmp}/d061.json")
            manager = FakeManager(coordinator, behavior="postcommit-warning")
            app = types.SimpleNamespace(rd_managed_live_adoption=coordinator)
            intent_file = f"{tmp}/release.json"
            install_adopted_hands_off_release_retirement(
                app, manager, intent_file=intent_file
            )

            with self.assertRaisesRegex(RuntimeSafetyError, "ACK lost"):
                await manager.enter_hands_off()

            self.assertTrue(manager.hands_off)
            self.assertEqual(coordinator.state, ManagedAdoptionState.INTERRUPTED)
            self.assertEqual(coordinator.verified_off_calls, 0)
            self.assertFalse(os.path.exists(intent_file))

    async def test_precommit_failure_preserves_managed_d061_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            coordinator = FakeCoordinator(f"{tmp}/d061.json")
            manager = FakeManager(coordinator, behavior="precommit-fail")
            app = types.SimpleNamespace(rd_managed_live_adoption=coordinator)
            intent_file = f"{tmp}/release.json"
            install_adopted_hands_off_release_retirement(
                app, manager, intent_file=intent_file
            )

            with self.assertRaisesRegex(RuntimeSafetyError, "precommit failed"):
                await manager.enter_hands_off()

            self.assertTrue(manager.pb_managed)
            self.assertTrue(coordinator.active)
            self.assertEqual(coordinator.verified_off_calls, 0)
            self.assertFalse(os.path.exists(intent_file))

    async def test_off_pending_cannot_be_converted_into_hands_off_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            coordinator = FakeCoordinator(
                f"{tmp}/d061.json", state=ManagedAdoptionState.OFF_PENDING
            )
            manager = FakeManager(coordinator)
            app = types.SimpleNamespace(rd_managed_live_adoption=coordinator)
            install_adopted_hands_off_release_retirement(
                app, manager, intent_file=f"{tmp}/release.json"
            )

            with self.assertRaisesRegex(RuntimeSafetyError, "verified Output OFF containment"):
                await manager.enter_hands_off()

            self.assertTrue(manager.pb_managed)
            self.assertEqual(coordinator.state, ManagedAdoptionState.OFF_PENDING)

    async def test_restart_hands_off_plus_matching_intent_retires_stale_off_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = f"{tmp}/d061.json"
            intent_file = f"{tmp}/release.json"
            coordinator = FakeCoordinator(
                state_file,
                state=ManagedAdoptionState.OFF_PENDING,
                session_id="d061-restart",
            )
            manager = FakeManager(coordinator, mode=RdControlMode.HANDS_OFF)
            app = types.SimpleNamespace(rd_managed_live_adoption=coordinator)
            self._intent(intent_file, "d061-restart")

            install_adopted_hands_off_release_retirement(
                app, manager, intent_file=intent_file
            )

            self.assertEqual(coordinator.state, ManagedAdoptionState.INTERRUPTED)
            self.assertEqual(coordinator.verified_off_calls, 0)
            self.assertFalse(os.path.exists(intent_file))

    async def test_restart_pb_managed_does_not_consume_release_marker_as_external_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = f"{tmp}/d061.json"
            intent_file = f"{tmp}/release.json"
            coordinator = FakeCoordinator(
                state_file,
                state=ManagedAdoptionState.OFF_PENDING,
                session_id="d061-managed",
            )
            manager = FakeManager(coordinator, mode=RdControlMode.PB_MANAGED)
            app = types.SimpleNamespace(rd_managed_live_adoption=coordinator)
            self._intent(intent_file, "d061-managed")

            install_adopted_hands_off_release_retirement(
                app, manager, intent_file=intent_file
            )

            self.assertEqual(coordinator.state, ManagedAdoptionState.OFF_PENDING)
            self.assertFalse(os.path.exists(intent_file))
            self.assertTrue(await coordinator._verified_off("managed restart containment"))
            self.assertEqual(coordinator.verified_off_calls, 1)

    async def test_unmatched_release_marker_never_retires_d061(self):
        with tempfile.TemporaryDirectory() as tmp:
            coordinator = FakeCoordinator(
                f"{tmp}/d061.json",
                state=ManagedAdoptionState.OFF_PENDING,
                session_id="current",
            )
            manager = FakeManager(coordinator, mode=RdControlMode.HANDS_OFF)
            app = types.SimpleNamespace(rd_managed_live_adoption=coordinator)
            intent_file = f"{tmp}/release.json"
            self._intent(intent_file, "other-session")

            install_adopted_hands_off_release_retirement(
                app, manager, intent_file=intent_file
            )

            self.assertEqual(coordinator.state, ManagedAdoptionState.OFF_PENDING)
            self.assertTrue(os.path.exists(intent_file))


if __name__ == "__main__":
    unittest.main()
