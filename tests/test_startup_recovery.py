import asyncio
import types
import unittest
from unittest import mock
from pathlib import Path

from runtime.startup_recovery import StartupRecovery


class _Managed:
    def __init__(self, result=True):
        self.result = result
        self.calls = 0

    async def recover_startup(self):
        self.calls += 1
        return self.result


class StartupRecoveryTests(unittest.TestCase):
    def test_guarded_candidate_stays_quarantined_without_native_snapshot(self):
        from application.execution_port import ExecutionPort
        from application.guard_execution_owner_lock import GuardExecutionOwnerLock
        from application.session_recovery_guard import SessionRecoveryGuard
        from runtime.charge.session import GuardedRestoreCandidate
        app = types.SimpleNamespace()
        app.charge_controller = types.SimpleNamespace(
            is_active=False,
            _guarded_restore_candidate=GuardedRestoreCandidate(
                {"main_current_guard_v1": {"revision": 2}}, "sid", "bat", 2,
                "direct_native_pre_on_reconciliation_required",
            ),
        )
        app.execution_port = ExecutionPort(object(), SessionRecoveryGuard())
        app.execution_port.bind_guard_owner_lock(GuardExecutionOwnerLock())
        app.hass = types.SimpleNamespace(get_all_live=mock.AsyncMock(
            side_effect=AssertionError("Guard recovery must not use HA aggregate")
        ))
        recovery = StartupRecovery(app, _Managed(), _Managed())
        asyncio.run(recovery.replay_deferred_startup_restore())
        app.hass.get_all_live.assert_not_awaited()
        self.assertEqual(app.charge_controller._guarded_restore_candidate.guard_revision, 2)

    def test_startup_and_deferred_restore_barriers_precede_restore(self):
        lifecycle = Path("runtime/production_lifecycle.py").read_text(encoding="utf-8")
        guard_check = lifecycle.index("may_run_automatic_control()")
        restore = lifecycle.index("controller.try_restore_session")
        self.assertLess(guard_check, restore)
        deferred = Path("runtime/startup_recovery.py").read_text(encoding="utf-8")
        guard_check = deferred.index("may_run_automatic_control()")
        restore = deferred.index("controller.try_restore_session")
        self.assertLess(guard_check, restore)

    def test_recovery_order_is_managed_mix_then_live_then_observer(self):
        events = []

        class Managed:
            def __init__(self, name):
                self.name = name

            async def recover_startup(self):
                events.append(self.name)
                return True

        app = types.SimpleNamespace()
        coordinator = StartupRecovery(
            app,
            Managed("mix"),
            Managed("live"),
            Managed("observer"),
        )
        with mock.patch(
            "runtime.startup_recovery.recover_diagnostic_persistence",
            new=mock.AsyncMock(),
        ) as recover_diagnostics:
            self.assertTrue(asyncio.run(coordinator.recover_managed_startup_authority()))
            recover_diagnostics.assert_awaited_once_with(app)
        self.assertEqual(events, ["mix", "live", "observer"])

    def test_failed_ownership_recovery_short_circuits(self):
        mix = _Managed(False)
        live = _Managed(True)
        coordinator = StartupRecovery(types.SimpleNamespace(), mix, live)

        self.assertFalse(asyncio.run(coordinator.recover_managed_startup_authority()))
        self.assertEqual(mix.calls, 1)
        self.assertEqual(live.calls, 0)

    def test_durable_quarantine_blocks_all_startup_authority_recovery(self):
        from application.session_recovery_guard import SessionRecoveryGuard
        app = types.SimpleNamespace(hass=object(), session_recovery_guard=SessionRecoveryGuard())
        app.session_recovery_guard.quarantine("prior_incident")
        mix = _Managed(True)
        live = _Managed(True)
        coordinator = StartupRecovery(app, mix, live)
        self.assertFalse(asyncio.run(coordinator.recover_managed_startup_authority()))
        self.assertEqual((mix.calls, live.calls), (0, 0))


if __name__ == "__main__":
    unittest.main()
