import asyncio
import ast
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
    def test_deferred_restore_cancellation_quarantines_and_reraises(self):
        from application.execution_port import ExecutionPort
        from application.guard_execution_owner_lock import GuardExecutionOwnerLock
        from application.session_recovery_guard import SessionRecoveryGuard
        guard = SessionRecoveryGuard()
        app = types.SimpleNamespace(
            charge_controller=types.SimpleNamespace(is_active=False, _guarded_restore_candidate=None),
            hass=types.SimpleNamespace(),
        )
        app.execution_port = ExecutionPort(object(), guard, app=app)
        app.execution_port.bind_guard_owner_lock(GuardExecutionOwnerLock())
        app.execution_port.read_live = mock.AsyncMock(side_effect=asyncio.CancelledError())
        recovery = StartupRecovery(app, _Managed(), _Managed())

        async def invoke():
            with mock.patch("runtime.startup_recovery.get_or_create_execution_port",
                            return_value=app.execution_port):
                with self.assertRaises(asyncio.CancelledError):
                    await recovery.replay_deferred_startup_restore()
        asyncio.run(invoke())
        self.assertTrue(guard.quarantined)
        self.assertEqual(guard.state.reason, "deferred_restore_cancelled")
        app.execution_port.read_live.assert_awaited_once()

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

    def test_startup_restore_exception_quarantines_before_background_control_starts(self):
        source = Path("runtime/production_lifecycle.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        restore = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "try_restore_session"
        )
        parent = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parent[child] = node
        restore_try = parent[restore]
        while not isinstance(restore_try, ast.Try):
            restore_try = parent[restore_try]
        exception_handler = next(
            (handler for handler in restore_try.handlers
             if isinstance(handler.type, ast.Name) and handler.type.id == "Exception"),
            None,
        )
        self.assertIsNotNone(exception_handler)
        failed_quarantine = ast.parse(
            "execution_port.session_recovery_guard.quarantine("
            "'startup_restore_failed:' + type(ex).__name__)"
        ).body[0].value
        self.assertIn(
            ast.dump(failed_quarantine),
            [ast.dump(node) for node in ast.walk(exception_handler)],
        )
        self.assertTrue(any(
            isinstance(node, ast.Raise) and node.exc is None
            for node in ast.walk(exception_handler)
        ), "Exception handler must re-raise after quarantining")
        enclosing = parent[restore_try]
        while not isinstance(enclosing, ast.Try):
            enclosing = parent[enclosing]
        cancellation_handler = next(
            (handler for handler in enclosing.handlers
             if isinstance(handler.type, ast.Attribute)
             and handler.type.attr == "CancelledError"
             and isinstance(handler.type.value, ast.Name)
             and handler.type.value.id == "asyncio"),
            None,
        )
        self.assertIsNotNone(cancellation_handler)
        cancelled_quarantine = ast.parse(
            "execution_port.session_recovery_guard.quarantine('startup_restore_cancelled')",
            mode="eval",
        ).body
        self.assertIn(
            ast.dump(cancelled_quarantine),
            [ast.dump(node) for node in ast.walk(cancellation_handler)],
        )
        self.assertTrue(any(
            isinstance(node, ast.Raise) and node.exc is None
            for node in ast.walk(cancellation_handler)
        ), "CancelledError handler must re-raise after quarantining")
        background_start = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "start_background_tasks"
            and any(isinstance(arg, ast.Attribute) and arg.attr == "charge_monitor"
                    for arg in node.args)
        )
        self.assertGreater(background_start.lineno, enclosing.lineno)

    def test_deferred_restore_live_read_uses_execution_port_safety_owner(self):
        source = Path("runtime/startup_recovery.py").read_text(encoding="utf-8")
        self.assertIn("live = await execution_port.read_live()", source)
        self.assertNotIn("live = await app.hass.get_all_live()", source)

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
