"""Application ownership for controller batch execution and verified commit."""

import ast
from pathlib import Path
import unittest
from types import SimpleNamespace

from application.controller_action_execution import execute_controller_action_batch


ROOT = Path(__file__).resolve().parents[1]


class _Port:
    def __init__(self, *, enabled=True):
        self.enabled = enabled
        self.calls = []

    async def execute_controller_actions(self, actions, live, **kwargs):
        self.calls.append(("execute", actions, live, kwargs))
        return SimpleNamespace(
            enabled=self.enabled,
            final_targets_missing=False,
            final_verification_failed=False,
        )

    async def request_verified_off(self):
        self.calls.append(("off",))
        return True


class _Controller:
    current_stage = "SAFE_WAIT"

    def __init__(self, commit):
        self.commit = commit
        self.commits = []
        self._last_known_output_on = False

    def commit_verified_enable_transition(self, transition, **kwargs):
        self.commits.append((transition, kwargs))
        return self.commit


class ApplicationActionExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def _execute(self, *, enabled, commit):
        port, controller = _Port(enabled=enabled), _Controller(commit)
        notices, events = [], []
        result = await execute_controller_action_batch(
            {"turn_on": True, "verified_enable_transition": {"kind": "safe_wait"}},
            {"switch": "off"},
            execution_port=port, controller=controller,
            battery_v=14.1, current=0.2, temp=24.0, ah=3.0,
            max_stage_current_a=12.0, ocp_offset_a=0.1,
            idle_safe_ocp_a=12.0, stabilize_delay_s=2.0,
            recipe_voltage_ceiling_v=16.6, has_ovp=True, has_ocp=True,
            notify=lambda *args, **kwargs: notices.append((args, kwargs)),
            log_event=lambda *args: events.append(args),
            logger=SimpleNamespace(warning=lambda *_: None, error=lambda *_: None),
            now=lambda: 123.0,
        )
        return result, port, controller, notices, events

    async def test_commit_follows_physical_verification_and_keeps_effects(self):
        commit = {"log_event": "verified", "notify": "ready"}
        result, port, controller, notices, events = await self._execute(enabled=True, commit=commit)
        self.assertTrue(result)
        self.assertEqual(port.calls[0][0], "execute")
        self.assertEqual(controller.commits[0][1], {
            "now": 123.0, "voltage": 14.1, "current": 0.2, "ah": 3.0,
        })
        self.assertTrue(controller._last_known_output_on)
        self.assertEqual(events[0][-1], "verified")
        self.assertEqual(notices, [(('ready',), {"critical": False})])

    async def test_missing_commit_after_enable_requests_verified_off(self):
        result, port, controller, _notices, _events = await self._execute(enabled=True, commit=None)
        self.assertFalse(result)
        self.assertEqual([call[0] for call in port.calls], ["execute", "off"])
        self.assertFalse(controller._last_known_output_on)

    async def test_runtime_adapter_delegates_to_application_owner(self):
        runtime = (ROOT / "runtime/production_runtime.py").read_text(encoding="utf-8")
        self.assertIn("return await execute_controller_action_batch(", runtime)
        start = runtime.index("async def _apply_controller_output_actions(")
        end = runtime.index("async def _hard_stop_charge(", start)
        adapter = ast.parse(runtime[start:end])
        called = [n for n in ast.walk(adapter) if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Name)
                  and n.func.id == "execute_controller_action_batch"]
        self.assertEqual(len(called), 1)
        self.assertFalse(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                             and n.func.attr in {"execute_controller_actions", "request_verified_off"}
                             for n in ast.walk(adapter)))


if __name__ == "__main__":
    unittest.main()
