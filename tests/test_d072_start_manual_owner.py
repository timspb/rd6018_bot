"""D072 source-only shared owner admission for automatic START and manual V/I."""
import asyncio
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

from application.execution_port import get_or_create_execution_port
from application.start_transaction_service import start_profile_transactional
from manual_runtime import _serialized_manual_normal_action
from runtime.startup_recovery import StartupRecovery


class FakeOwner:
    def __init__(self):
        self.events = []
        self.entered = asyncio.Event()
        self.release_voltage = asyncio.Event()

    async def get_all_live(self):
        self.events.append(("get_live",))
        return {}

    async def set_voltage(self, value):
        self.events.append(("voltage_start", float(value)))
        self.entered.set()
        await self.release_voltage.wait()
        self.events.append(("voltage_end", float(value)))
        return True

    async def set_current(self, value):
        self.events.append(("current", float(value)))
        return True

    async def turn_off(self):
        self.events.append(("emergency_off",))
        return True


class D072OwnerTransactionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.owner = FakeOwner()
        self.app = SimpleNamespace(
            hass=self.owner,
            charge_controller=SimpleNamespace(is_active=True),
        )
        self.port = get_or_create_execution_port(self.app)

    async def test_start_preflight_waits_for_same_app_owner(self):
        answers = []
        class Message:
            from_user = None
            async def answer(self, value, **kwargs):
                answers.append(value)

        async with self.port._guard_owner_lock:
            start = asyncio.create_task(start_profile_transactional(
                self.app, Message(), None
            ))
            await asyncio.sleep(0)
            self.assertFalse(start.done())
            self.assertEqual(answers, [])
        result = await asyncio.wait_for(start, timeout=1)
        self.assertFalse(result)
        self.assertEqual(len(answers), 1)
        self.assertIn("остановите текущую программу", answers[0])

    async def test_manual_pair_keeps_v_and_i_together_against_other_normal_setters(self):
        first = asyncio.create_task(self.port.program_voltage_current(14.4, 4.0))
        await asyncio.wait_for(self.owner.entered.wait(), timeout=1)
        racing = asyncio.create_task(self.port.program_current(3.0))
        await asyncio.sleep(0)
        self.assertEqual(self.owner.events, [("voltage_start", 14.4)])
        self.assertFalse(racing.done())

        # OFF is deliberately not queued behind an ordinary setter transaction.
        self.assertTrue(await asyncio.wait_for(self.port.request_verified_off(), timeout=1))
        self.assertEqual(self.owner.events[-1], ("emergency_off",))
        self.owner.release_voltage.set()

        self.assertEqual(await asyncio.wait_for(first, timeout=1), (True, True))
        self.assertTrue(await asyncio.wait_for(racing, timeout=1))
        self.assertEqual(self.owner.events, [
            ("voltage_start", 14.4), ("emergency_off",),
            ("voltage_end", 14.4), ("current", 4.0), ("current", 3.0),
        ])

    async def test_manual_start_preflight_uses_same_lock_as_auto_start(self):
        entered = []
        class ManualProbe:
            def __init__(self, app):
                self.app = app

            @_serialized_manual_normal_action
            async def start(self):
                entered.append("manual-entered")
                return True

        probe = ManualProbe(self.app)
        async with self.port._guard_owner_lock:
            action = asyncio.create_task(probe.start())
            await asyncio.sleep(0)
            self.assertFalse(action.done())
            self.assertEqual(entered, [])
        self.assertTrue(await asyncio.wait_for(action, timeout=1))
        self.assertEqual(entered, ["manual-entered"])

    async def test_deferred_restore_waits_for_same_owner_lock(self):
        self.app._operator_pause_active = lambda: True
        self.app.logger = SimpleNamespace(info=lambda *args, **kwargs: None)
        coordinator = StartupRecovery(self.app, None, None)
        async with self.port._guard_owner_lock:
            task = asyncio.create_task(coordinator.replay_deferred_startup_restore())
            await asyncio.sleep(0)
            self.assertFalse(task.done())
            self.assertEqual(self.owner.events, [])
        await asyncio.wait_for(task, timeout=1)
        self.assertEqual(self.owner.events, [("get_live",)])

    def test_initial_restore_and_shutdown_journal_use_one_owner_scope(self):
        path = Path(__file__).resolve().parents[1] / "runtime" / "production_lifecycle.py"
        module = ast.parse(path.read_text(encoding="utf-8"))
        cls = next(
            n for n in module.body
            if isinstance(n, ast.ClassDef) and n.name == "ProductionRuntimeLifecycle"
        )
        for method, required_calls in (
            ("run", ("controller.try_restore_session", "execution_port.request_verified_on")),
            ("on_shutdown", ("app.charge_controller._save_session",)),
        ):
            fn = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == method)
            owners = []
            for n in ast.walk(fn):
                if not isinstance(n, ast.AsyncWith):
                    continue
                if not any("_guard_owner_lock" in ast.unparse(item.context_expr) for item in n.items):
                    continue
                calls = {
                    ast.unparse(x.func)
                    for statement in n.body for x in ast.walk(statement)
                    if isinstance(x, ast.Call)
                }
                if all(call in calls for call in required_calls):
                    owners.append(n)
            self.assertEqual(len(owners), 1, method)

    def test_manual_lifecycle_methods_are_explicitly_serialized(self):
        path = Path(__file__).resolve().parents[1] / "manual_runtime.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        manual = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "ProductionManualSessionManager"
        )
        for method in ("start", "replace", "_resume_after_cooling"):
            fn = next(n for n in manual.body if isinstance(n, ast.AsyncFunctionDef) and n.name == method)
            self.assertIn("_serialized_manual_normal_action",
                          [ast.unparse(d) for d in fn.decorator_list])

    async def test_manual_pair_uses_one_production_port_owner(self):
        self.owner.release_voltage.set()
        self.assertIs(get_or_create_execution_port(self.app), self.port)
        self.assertIs(self.app.guard_execution_owner_lock, self.port._guard_owner_lock)
        self.assertEqual(await self.port.program_voltage_current(13.8, 2.0), (True, True))
        self.assertFalse(self.port._guard_owner_lock.locked())

    def test_link_recovery_and_in_memory_restore_are_locked_with_tick(self):
        path = Path(__file__).resolve().parents[1] / "runtime" / "production_runtime.py"
        module = ast.parse(path.read_text(encoding="utf-8"))
        data_logger = next(n for n in ast.walk(module)
                           if isinstance(n, ast.AsyncFunctionDef) and n.name == "data_logger")
        candidates = []
        for node in ast.walk(data_logger):
            if not isinstance(node, ast.AsyncWith):
                continue
            if not any("_runtime_execution_port()._guard_owner_lock" in ast.unparse(item.context_expr)
                       for item in node.items):
                continue
            calls = [
                ast.unparse(child.func)
                for stmt in node.body for child in ast.walk(stmt)
                if isinstance(child, ast.Call)
            ]
            if ("charge_controller.tick" in calls and
                calls.count("charge_controller.try_restore_session") >= 2 and
                "_runtime_execution_port().request_verified_on" in calls):
                candidates.append(node)
        self.assertEqual(len(candidates), 1)

    def test_periodic_tick_and_physical_action_share_one_owner_scope(self):
        """AST coverage gate: neither stage checkpoint nor output batch can bypass lock."""
        path = Path(__file__).resolve().parents[1] / "runtime" / "production_runtime.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        loggers = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "data_logger"
        ]
        self.assertEqual(len(loggers), 1)
        locked = []
        for node in ast.walk(loggers[0]):
            if not isinstance(node, ast.AsyncWith):
                continue
            guard = " ".join(ast.unparse(item.context_expr) for item in node.items)
            if "_runtime_execution_port()._guard_owner_lock" not in guard:
                continue
            calls = {
                ast.unparse(n.func) for stmt in node.body for n in ast.walk(stmt)
                if isinstance(n, ast.Call)
            }
            if {"charge_controller.tick", "_apply_controller_output_actions"} <= calls:
                locked.append(node)
        self.assertEqual(len(locked), 1)
        # Guard state is still software only: locking cannot be mistaken for a
        # runtime call to execute_main_current_guard_reduction.
        self.assertNotIn("execute_main_current_guard_reduction(",
                         path.read_text(encoding="utf-8"))

    def test_both_legacy_manual_text_formats_use_atomic_port_pair(self):
        runtime_path = Path(__file__).resolve().parents[1] / "runtime" / "production_runtime.py"
        source = runtime_path.read_text(encoding="utf-8")
        self.assertEqual(
            source.count("ok_v, ok_i = await _runtime_execution_port().program_voltage_current("),
            2,
        )


if __name__ == "__main__":
    unittest.main()
