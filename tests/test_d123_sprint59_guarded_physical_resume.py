"""Synthetic endpoint tests for the D123 Sprint 59 resume receipt gate."""
import asyncio
from types import SimpleNamespace
import unittest

from application.execution_port import ExecutionPort
from application.guard_execution_owner_lock import GuardExecutionOwnerLock
from application.session_recovery_guard import SessionRecoveryGuard
from runtime.charge.session import GuardedPhysicalResumePermit, _GUARDED_PHYSICAL_RESUME_SEAL


class Sprint59ExecutionPortTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.controller = SimpleNamespace(_guarded_restore_activated_off=True)
        self.lock = GuardExecutionOwnerLock()
        self.port = ExecutionPort(object(), SessionRecoveryGuard())
        self.port.bind_guard_owner_lock(self.lock)
        self.port.mark_guarded_restore_activated_off()
        self.permit = None

    def make_permit(self):
        return GuardedPhysicalResumePermit(
            "sid", "bid", 1, (), 1, asyncio.current_task(), self.lock,
            self.controller, 1, "digest", "bytes", _GUARDED_PHYSICAL_RESUME_SEAL,
        )

    async def test_source_only_ready_and_replay_blocked(self):
        self.permit = self.make_permit()
        async with self.lock:
            result = await self.port.execute_guarded_physical_resume(self.permit)
            replay = await self.port.execute_guarded_physical_resume(self.permit)
        self.assertEqual(result.state, "READY_BUT_NOT_EXECUTED")
        self.assertEqual(replay.state, "BLOCKED")
        self.assertTrue(self.port.guarded_restore_activated_off)
        self.assertTrue(self.controller._guarded_restore_activated_off)

    async def test_synthetic_verified_receipt_clears_both_latches_once(self):
        self.permit = self.make_permit()
        calls = []
        async def fake_endpoint(permit):
            calls.append(permit)
            return SimpleNamespace(verified_on=True)
        self.port._guarded_resume_endpoint = fake_endpoint
        async with self.lock:
            result = await self.port.execute_guarded_physical_resume(self.permit)
            replay = await self.port.execute_guarded_physical_resume(self.permit)
        self.assertEqual(result.state, "VERIFIED_ON_COMMITTED")
        self.assertEqual(replay.state, "BLOCKED")
        self.assertEqual(calls, [self.permit])
        self.assertFalse(self.port.guarded_restore_activated_off)
        self.assertFalse(self.controller._guarded_restore_activated_off)

    async def test_failed_synthetic_endpoint_keeps_both_latches(self):
        self.permit = self.make_permit()
        async def fake_endpoint(_permit):
            return SimpleNamespace(verified_on=False)
        self.port._guarded_resume_endpoint = fake_endpoint
        async with self.lock:
            result = await self.port.execute_guarded_physical_resume(self.permit)
        self.assertEqual(result.state, "BLOCKED")
        self.assertTrue(self.port.guarded_restore_activated_off)
        self.assertTrue(self.controller._guarded_restore_activated_off)


if __name__ == "__main__":
    unittest.main()
