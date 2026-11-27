"""B1060: FC03-causal receipt; durable quarantine exposes operator UI only."""
import asyncio
import contextvars
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from rd_startup_authority import RdStartupAuthorityGate


class QuarantineOnlyStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_durable_incident_starts_only_operator_ui(self):
        gate = RdStartupAuthorityGate.__new__(RdStartupAuthorityGate)
        class Guard:
            async def _raw_live(self):
                return {"autonomous_mode": False}
        class Manager:
            edge_autonomous = False
            pb_managed = True
            def _observe_edge_mode(self, raw): pass
            def _record_edge_autonomous(self, value): pass
        persisted = SimpleNamespace(quarantined=True)
        memory_guard = SimpleNamespace(quarantined=True, _durable=True)
        gate.app = SimpleNamespace(
            execution_port=SimpleNamespace(session_recovery_guard=memory_guard),
            recovery_quarantine_journal=SimpleNamespace(load=lambda: persisted),
        )
        gate.guard = Guard()
        gate.manager = Manager()
        gate._recovery_scope = contextvars.ContextVar("b1060_scope", default=False)
        gate._deferred_restore_requested = True
        calls = 0
        async def fail_recovery():
            nonlocal calls
            calls += 1
            return False
        result = await asyncio.wait_for(gate.reconcile(fail_recovery), timeout=0.5)
        self.assertEqual(result, "managed_quarantined")
        self.assertEqual(calls, 1)
        self.assertFalse(gate.managed_actuation_ready)
        self.assertFalse(gate.nonautonomous_ready)
        self.assertFalse(gate.managed_recovery_complete)
        self.assertFalse(gate.deferred_restore_requested)
        self.assertTrue(memory_guard.quarantined)
        self.assertTrue(persisted.quarantined)

    async def test_missing_durable_journal_never_admits_ui(self):
        gate = RdStartupAuthorityGate.__new__(RdStartupAuthorityGate)
        gate.app = SimpleNamespace(
            execution_port=SimpleNamespace(session_recovery_guard=
                SimpleNamespace(quarantined=True, _durable=True)),
            recovery_quarantine_journal=None)
        self.assertFalse(gate._durable_quarantine_ui_eligible())
        gate.app.recovery_quarantine_journal = SimpleNamespace(
            load=lambda: SimpleNamespace(quarantined=False))
        self.assertFalse(gate._durable_quarantine_ui_eligible())
        gate.app.recovery_quarantine_journal = SimpleNamespace(load=lambda: (_ for _ in ()).throw(ValueError()))
        self.assertFalse(gate._durable_quarantine_ui_eligible())
