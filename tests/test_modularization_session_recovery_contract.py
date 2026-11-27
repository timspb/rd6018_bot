"""Fake-only observable contract tests for SessionRecoveryService.

These tests deliberately instantiate the application service directly. They do
not import the production runtime, bot, HA, ESP, or any device adapter.
"""

import unittest
import ast
from pathlib import Path

from application.session_recovery_guard import SessionRecoveryGuard
from application.session_recovery_service import (
    RecoveryExecutionResult,
    SessionRecoveryService,
)


class FakeRecoveryPort:
    def __init__(self):
        self.calls = []
        self.reject = set()
        self.raise_on = set()

    async def _record(self, name, value=None):
        self.calls.append((name, value) if value is not None else (name,))
        if name in self.raise_on:
            raise RuntimeError(name)
        return name not in self.reject

    async def program_voltage(self, value_v):
        return await self._record("voltage", value_v)

    async def program_current(self, value_a):
        return await self._record("current", value_a)

    async def request_verified_off(self):
        return await self._record("verified_off")

    async def request_verified_on(self):
        return await self._record("verified_on")


class SessionRecoveryContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.port = FakeRecoveryPort()
        self.guard = SessionRecoveryGuard()
        self.service = SessionRecoveryService(
            self.port, lambda amps: min(10.0, amps), self.guard
        )

    async def test_reenable_active_orders_voltage_capped_current_then_verified_on(self):
        self.assertTrue(await self.service.reenable_active(14.4, 12.0))
        self.assertEqual(self.port.calls, [
            ("voltage", 14.4), ("current", 10.0), ("verified_on",)
        ])
        self.assertFalse(self.guard.quarantined)

    async def test_reenable_denials_quarantine_and_stop_at_failed_step(self):
        expected = {
            "voltage": [("voltage", 14.4)],
            "current": [("voltage", 14.4), ("current", 10.0)],
            "verified_on": [
                ("voltage", 14.4), ("current", 10.0), ("verified_on",)
            ],
        }
        for denied, calls in expected.items():
            with self.subTest(denied=denied):
                self.guard = SessionRecoveryGuard()
                self.service = SessionRecoveryService(
                    self.port, lambda amps: min(10.0, amps), self.guard
                )
                self.port.calls.clear()
                self.port.reject = {denied}
                self.assertFalse(await self.service.reenable_active(14.4, 12.0))
                self.assertTrue(self.guard.quarantined)
                self.assertEqual(self.guard.state.reason, denied.removeprefix("verified_") if denied != "verified_on" else "verified_on")
                self.assertEqual(self.port.calls, calls)

    async def test_quarantine_blocks_all_routes_without_port_calls(self):
        self.guard.quarantine("prior_failure")
        self.assertFalse(await self.service.reenable_active(14.4, 2.0))
        idle = await self.service.restore_idle_link(14.4, 2.0, safe_wait=False)
        output = await self.service.restore_output_on(14.4, 2.0, safe_wait=False)
        self.assertEqual(idle, RecoveryExecutionResult(False, "session_recovery_quarantined"))
        self.assertEqual(output, RecoveryExecutionResult(False, "session_recovery_quarantined"))
        self.assertEqual(self.port.calls, [])

    async def test_idle_safe_wait_programs_targets_then_verified_off_only(self):
        result = await self.service.restore_idle_link(13.5, 2.0, safe_wait=True)
        self.assertEqual(result, RecoveryExecutionResult(True, output_confirmed=False))
        self.assertEqual(self.port.calls, [
            ("voltage", 13.5), ("current", 2.0), ("verified_off",)
        ])
        self.assertNotIn(("verified_on",), self.port.calls)

    async def test_idle_normal_path_requests_verified_on_after_setpoints(self):
        result = await self.service.restore_idle_link(14.4, 2.0, safe_wait=False)
        self.assertEqual(result, RecoveryExecutionResult(True, output_confirmed=True))
        self.assertEqual(self.port.calls, [
            ("voltage", 14.4), ("current", 2.0), ("verified_on",)
        ])

    async def test_idle_verified_on_denial_quarantines_and_retry_is_idempotently_blocked(self):
        self.port.reject = {"verified_on"}
        failed = await self.service.restore_idle_link(14.4, 2.0, safe_wait=False)
        self.assertEqual(failed, RecoveryExecutionResult(False, "verified_on"))
        self.assertTrue(self.guard.quarantined)
        first_calls = list(self.port.calls)
        self.port.reject.clear()
        retry = await self.service.restore_idle_link(14.4, 2.0, safe_wait=False)
        self.assertEqual(retry, RecoveryExecutionResult(False, "session_recovery_quarantined"))
        self.assertEqual(self.port.calls, first_calls)

    async def test_idle_setpoint_or_off_denial_quarantines_and_never_enables(self):
        scenarios = (("voltage", "voltage"), ("current", "current"),
                     ("verified_off", "verified_off"))
        for denied, failed_step in scenarios:
            with self.subTest(denied=denied):
                self.guard = SessionRecoveryGuard()
                self.service = SessionRecoveryService(
                    self.port, lambda amps: min(10.0, amps), self.guard
                )
                self.port.calls.clear()
                self.port.reject = {denied}
                result = await self.service.restore_idle_link(
                    13.5, 2.0, safe_wait=True
                )
                self.assertEqual(result.failed_step, failed_step)
                self.assertFalse(result.confirmed)
                self.assertTrue(self.guard.quarantined)
                self.assertNotIn(("verified_on",), self.port.calls)
        self.port.reject.clear()

    async def test_restore_output_on_exact_current_contract_and_gap(self):
        # safe_wait=False: setpoints are accepted, but ON is neither requested
        # nor confirmed. This is intentionally asserted as implemented.
        result = await self.service.restore_output_on(14.4, 2.0, safe_wait=False)
        self.assertEqual(result, RecoveryExecutionResult(True, output_confirmed=None))
        self.assertEqual(self.port.calls, [("voltage", 14.4), ("current", 2.0)])
        self.assertNotIn(("verified_on",), self.port.calls)

        # safe_wait=True starts with verified OFF, then programs V/I; it still
        # never requests ON and records output_confirmed=False.
        self.port.calls.clear()
        result = await self.service.restore_output_on(13.5, 2.0, safe_wait=True)
        self.assertEqual(result, RecoveryExecutionResult(True, output_confirmed=False))
        self.assertEqual(self.port.calls, [
            ("verified_off",), ("voltage", 13.5), ("current", 2.0)
        ])
        self.assertNotIn(("verified_on",), self.port.calls)

    async def test_restore_output_on_denial_quarantines_and_reports_failed_step(self):
        for denied in ("verified_off", "voltage", "current"):
            with self.subTest(denied=denied):
                self.guard = SessionRecoveryGuard()
                self.service = SessionRecoveryService(
                    self.port, lambda amps: min(10.0, amps), self.guard
                )
                self.port.calls.clear()
                self.port.reject = {denied}
                result = await self.service.restore_output_on(
                    13.5, 2.0, safe_wait=True
                )
                self.assertFalse(result.confirmed)
                expected_step = "verified_off" if denied == "verified_off" else denied
                self.assertEqual(result.failed_step, expected_step)
                self.assertTrue(self.guard.quarantined)
                self.assertNotIn(("verified_on",), self.port.calls)
        self.port.reject.clear()

    async def test_exception_is_quarantined_then_propagated(self):
        self.port.raise_on = {"verified_on"}
        with self.assertRaisesRegex(RuntimeError, "verified_on"):
            await self.service.restore_idle_link(14.4, 2.0, safe_wait=False)
        self.assertTrue(self.guard.quarantined)
        self.assertEqual(self.guard.state.reason, "execution_exception")

    def test_recovery_cycle_is_extracted_and_keeps_locked_cycle_order(self):
        root = Path(__file__).resolve().parents[1]
        runtime_path = root / "runtime/production_runtime.py"
        source = runtime_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        data_logger = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "data_logger"
        )
        self.assertEqual(sum(
            isinstance(node, ast.Call)
            and ast.unparse(node.func) == "SessionRecoveryService.run_cycle"
            for node in ast.walk(data_logger)
        ), 1)
        self.assertFalse(any(
            isinstance(node, ast.Call)
            and ast.unparse(node.func) in {
                "choose_recovery_route", "controller.try_restore_session"
            }
            for node in ast.walk(data_logger)
        ))

        owner_lock = next(
            node for node in ast.walk(data_logger)
            if isinstance(node, ast.AsyncWith)
            and any(
                "_guard_owner_lock" in ast.unparse(item.context_expr)
                for item in node.items
            )
            and any(
                isinstance(child, ast.Call)
                and ast.unparse(child.func) == "SessionRecoveryService.run_cycle"
                for child in ast.walk(node)
            )
        )
        statement_source = ast.unparse(owner_lock)
        self.assertLess(statement_source.index("SessionRecoveryService.run_cycle"),
                        statement_source.index("run_main_guard_cycle"))
        self.assertLess(statement_source.index("run_main_guard_cycle"),
                        statement_source.index("run_charge_session_tick"))
        self.assertLess(statement_source.index("SessionRecoveryService.run_cycle"),
                        statement_source.index("now_ts = time.time()"))
        self.assertLess(statement_source.index("now_ts = time.time()"),
                        statement_source.index("run_main_guard_cycle"))


if __name__ == "__main__":
    unittest.main()
