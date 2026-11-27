"""Fake-only contracts for the extracted Manual stop application use case."""

import ast
import unittest
from enum import Enum
from pathlib import Path
from types import SimpleNamespace

from application.manual_stop_use_case import stop_manual_session
from v3_core.canonical_events import EventType


class State(str, Enum):
    ACTIVE = "active"
    STOPPED = "stopped"
    FAILED = "failed"


class FakeExecutionPort:
    def __init__(self, session):
        self.session = session
        self.result = SimpleNamespace(verified=True, reason="")
        self.error = None
        self.calls = []

    async def disable(self, intent, *, identity, reason):
        self.calls.append((intent, identity, reason, self.session.state))
        if self.error:
            raise self.error
        return self.result


class ManualStopUseCaseTests(unittest.IsolatedAsyncioTestCase):
    def make_session(self, identity=True):
        session = SimpleNamespace(state=State.ACTIVE, stop_reason="", cooling_started_at=12.0)
        session.persist_calls = 0
        session.events = []
        session.transitions = []
        session.identity_integration = SimpleNamespace(
            identity=SimpleNamespace(trace_id="trace-1") if identity else None,
            emit=lambda **kwargs: session.events.append((session.state, kwargs)),
        )
        def transition(state, reason):
            session.transitions.append((state, reason))
            session.state = state
        session._transition_state = transition
        session._persist = lambda: setattr(session, "persist_calls", session.persist_calls + 1)
        session.execution_port = FakeExecutionPort(session)
        return session

    async def test_verified_off_transitions_persists_and_emits_after_transition(self):
        session = self.make_session()
        confirmed = await stop_manual_session(session, "operator_requested")
        self.assertTrue(confirmed)
        self.assertEqual(session.execution_port.calls[0][0].requested_mode, "MANUAL_STOP")
        self.assertEqual(session.execution_port.calls[0][2], "operator_requested")
        self.assertEqual(session.execution_port.calls[0][3], State.ACTIVE)
        self.assertEqual(session.state, State.STOPPED)
        self.assertEqual(session.persist_calls, 1)
        self.assertIsNone(session.cooling_started_at)
        self.assertEqual(session.events[0][0], State.STOPPED)
        self.assertEqual(session.events[0][1]["event_type"], EventType.SESSION_STOPPED)
        self.assertEqual(session.events[0][1]["reason"], "operator_requested")

    async def test_unverified_off_fails_and_never_stops(self):
        session = self.make_session()
        session.execution_port.result = SimpleNamespace(verified=False, reason="off_denied")
        confirmed = await stop_manual_session(session, "operator_stop")
        self.assertFalse(confirmed)
        self.assertEqual(session.state, State.FAILED)
        self.assertNotIn(State.STOPPED, [state for state, _ in session.transitions])
        self.assertEqual(session.persist_calls, 1)
        self.assertEqual(session.events[0][1]["reason"], "operator_stop")

    async def test_disable_exception_still_fails_persists_and_propagates(self):
        session = self.make_session(identity=False)
        session.execution_port.error = ValueError("disable failed")
        with self.assertRaisesRegex(ValueError, "disable failed"):
            await stop_manual_session(session, "operator_stop")
        self.assertEqual(session.state, State.FAILED)
        self.assertEqual(session.persist_calls, 1)
        self.assertEqual(session.events, [])

    async def test_missing_identity_uses_legacy_source_and_emits_no_session_event(self):
        session = self.make_session(identity=False)
        await stop_manual_session(session)
        intent = session.execution_port.calls[0][0]
        self.assertEqual(intent.source_decision_id, "manual_stop:legacy")
        self.assertEqual(session.events, [])

    def test_manager_method_is_thin_delegate_and_application_imports_are_acyclic(self):
        source = Path("manual_mode.py").read_text(encoding="utf-8")
        module = ast.parse(source)
        manager = next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == "ManualSessionManager")
        method = next(n for n in manager.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "stop")
        self.assertEqual(len(method.body), 1)
        call = method.body[0].value
        self.assertIsInstance(call, ast.Await)
        self.assertEqual(ast.unparse(call.value), "stop_manual_session(self, reason)")

        use_case = ast.parse(Path("application/manual_stop_use_case.py").read_text(encoding="utf-8"))
        imported = [alias.name for node in ast.walk(use_case) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names]
        self.assertFalse(any(name == "manual_mode" or name == "runtime.production_runtime" for name in imported))


if __name__ == "__main__":
    unittest.main()
