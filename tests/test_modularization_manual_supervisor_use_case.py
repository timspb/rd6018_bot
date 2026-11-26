"""Fake-only contracts for the Manual session supervisor use case."""

import ast
import asyncio
import inspect
import textwrap
import unittest
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import application.manual_supervisor_use_case as supervisor
import manual_mode


class State(Enum):
    ACTIVE = "active"
    FAILED = "failed"


class FakeExecutionPort:
    def __init__(self, *, emergency_error=None):
        self.emergency_calls = []
        self.emergency_error = emergency_error

    async def request_emergency_off(self):
        self.emergency_calls.append(())
        if self.emergency_error is not None:
            raise self.emergency_error


def make_session(*, active=True, observe=None, emergency_error=None, identity=None):
    session = SimpleNamespace(
        is_active=active,
        state=State.ACTIVE,
        stop_reason="",
        identity_integration=SimpleNamespace(identity=identity),
        execution_port=FakeExecutionPort(emergency_error=emergency_error),
        observed=0,
        persisted=0,
        transitions=[],
    )

    async def observe_once():
        session.observed += 1
        if observe is not None:
            outcome = observe(session)
            if isinstance(outcome, BaseException):
                raise outcome

    def transition(state, reason):
        session.transitions.append((state, reason))
        session.state = state

    def persist():
        session.persisted += 1

    session.observe_once = observe_once
    session._transition_state = transition
    session._persist = persist
    return session


class ManualSupervisorUseCaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_inactive_session_does_not_observe_or_sleep(self):
        session = make_session(active=False)
        with mock.patch.object(supervisor.asyncio, "sleep", new=mock.AsyncMock()) as sleep:
            await supervisor.supervise_manual_session(session, poll_seconds=2.5)
        self.assertEqual(session.observed, 0)
        sleep.assert_not_awaited()

    async def test_deactivation_during_observation_skips_sleep(self):
        def deactivate(session):
            session.is_active = False

        session = make_session(observe=deactivate)
        with mock.patch.object(supervisor.asyncio, "sleep", new=mock.AsyncMock()) as sleep:
            await supervisor.supervise_manual_session(session, poll_seconds=2.5)
        self.assertEqual(session.observed, 1)
        sleep.assert_not_awaited()

    async def test_repeated_loop_sleeps_with_passed_interval(self):
        session = make_session()
        calls = 0

        async def sleep(seconds):
            nonlocal calls
            self.assertEqual(seconds, 3.25)
            calls += 1
            if calls == 2:
                session.is_active = False

        with mock.patch.object(supervisor.asyncio, "sleep", new=sleep):
            await supervisor.supervise_manual_session(session, poll_seconds=3.25)
        self.assertEqual(session.observed, 2)
        self.assertEqual(calls, 2)

    async def test_cancellation_propagates_without_failure_transition(self):
        session = make_session(observe=lambda _session: asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await supervisor.supervise_manual_session(session, poll_seconds=1.0)
        self.assertEqual(session.transitions, [])
        self.assertEqual(session.persisted, 0)
        self.assertEqual(session.execution_port.emergency_calls, [])

    async def test_observer_error_requests_emergency_off_then_persists_failed(self):
        identity = SimpleNamespace(trace_id="trace-123")
        session = make_session(observe=lambda _session: ValueError("fake"), identity=identity)
        await supervisor.supervise_manual_session(session, poll_seconds=1.0)
        self.assertEqual(session.execution_port.emergency_calls, [()])
        self.assertEqual(session.transitions, [(State.FAILED, "manual_runtime_error:ValueError")])
        self.assertEqual(session.persisted, 1)

    async def test_emergency_off_error_still_persists_failed_and_propagates(self):
        error = OSError("fake emergency OFF error")
        session = make_session(
            observe=lambda _session: ValueError("fake observer error"),
            emergency_error=error,
        )
        with self.assertRaisesRegex(OSError, "fake emergency OFF error"):
            await supervisor.supervise_manual_session(session, poll_seconds=1.0)
        self.assertEqual(session.execution_port.emergency_calls, [()])
        self.assertEqual(session.transitions, [(State.FAILED, "manual_runtime_error:ValueError")])
        self.assertEqual(session.persisted, 1)

    def test_adapter_is_thin_delegate_and_use_case_has_no_runtime_owner_import(self):
        method = manual_mode.ManualSessionManager._run
        source = inspect.getsource(method)
        tree = ast.parse(textwrap.dedent(source))
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
        self.assertEqual(len(calls), 1)
        self.assertEqual(ast.unparse(calls[0].func), "supervise_manual_session")
        self.assertEqual(ast.unparse(calls[0].args[0]), "self")
        self.assertEqual(ast.unparse(calls[0].keywords[0].value), "MANUAL_POLL_SEC")

        module_path = Path(supervisor.__file__)
        module_tree = ast.parse(module_path.read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(module_tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        self.assertFalse(any(name == "manual_mode" or name.endswith(".manual_mode") for name in imported))
        self.assertFalse(any(name == "runtime.production_runtime" for name in imported))


if __name__ == "__main__":
    unittest.main()
