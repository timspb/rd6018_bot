"""Architecture and behavioral proof for operator-pause owner cutover."""

import ast
import asyncio
import tempfile
import time
import types
import unittest
from pathlib import Path

from application.operator_pause_use_case import toggle_operator_pause
from runtime.operator.pause_state import OperatorPauseState


RUNTIME_SOURCE = Path(__file__).resolve().parents[1] / "runtime" / "production_runtime.py"


def _tree():
    return ast.parse(RUNTIME_SOURCE.read_text(encoding="utf-8"))


def _function_nodes(tree):
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


class FakePort:
    def __init__(self, live, events, *, on=True):
        self.live = live
        self.events = events
        self.on_result = on
        self.on_calls = 0
        self._guard_owner_lock = _AsyncLock()

    async def read_live(self):
        return dict(self.live)

    async def request_verified_off(self):
        self.live["switch"] = "off"
        return True

    async def request_verified_on(self):
        self.on_calls += 1
        self.events.append("verified_on")
        if self.on_result:
            self.live["switch"] = "on"
        return self.on_result

    async def program_voltage(self, _value):
        return True

    async def program_current(self, _value):
        return True


class _AsyncLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class FakeController:
    is_active = True
    current_stage = "CV"
    STAGE_SAFE_WAIT = "SAFE_WAIT"

    def __init__(self, events):
        self.events = events

    def _save_session(self, *_values):
        return None

    def _get_target_v_i(self, _temperature):
        return 14.7, 0.3

    def shift_active_clocks(self, _seconds):
        self.events.append("shift")


class OperatorPauseCutoverTests(unittest.TestCase):
    def test_single_owner_and_no_legacy_scalar_anywhere_in_runtime_ast(self):
        tree = _tree()
        owner_defs = []
        legacy_names = []
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(isinstance(target, ast.Name) and target.id == "_operator_pause_state"
                       for target in targets):
                    owner_defs.append(node)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "operator_pause_started_at":
                legacy_names.append(node)
        self.assertEqual(len(owner_defs), 1)
        self.assertIsInstance(owner_defs[0].value, ast.Call)
        self.assertEqual(owner_defs[0].value.func.id, "OperatorPauseState")
        self.assertEqual(legacy_names, [])

    def test_runtime_helpers_are_thin_pause_state_delegates(self):
        nodes = _function_nodes(_tree())
        expected = {
            "_operator_pause_active": "active",
            "_save_operator_pause_state": "save",
            "_load_operator_pause_state": "load",
            "_clear_operator_pause": "clear",
        }
        for function, method in expected.items():
            with self.subTest(function=function):
                calls = [node for node in ast.walk(nodes[function]) if isinstance(node, ast.Call)]
                self.assertTrue(any(
                    isinstance(call.func, ast.Attribute) and call.func.attr == method
                    for call in calls
                ))

    def test_verified_on_precedes_clock_shift_and_safe_wait_never_requests_on(self):
        with tempfile.TemporaryDirectory() as tempdir:
            now = time.time()
            events = []
            state = OperatorPauseState(now - 10.0)
            live = {
                "switch": "off",
                "battery_voltage": 14.6,
                "current": 0.4,
                "ah": 12.0,
                "temp_ext": 25.0,
                "input_voltage": 60.0,
            }
            port = FakePort(live, events)
            controller = FakeController(events)
            pause_file = str(Path(tempdir) / "pause.json")
            host = types.SimpleNamespace(
                hass=types.SimpleNamespace(
                    get_all_live=lambda: asyncio.sleep(0, result=dict(live))
                ),
                charge_controller=controller,
                _operator_pause_state=state,
                _operator_pause_active=state.active,
                _runtime_execution_port=lambda: port,
                _save_operator_pause_state=lambda: state.save(pause_file),
                _clear_operator_pause=lambda: state.clear(pause_file),
                _safe_float=lambda value, default=0.0: float(value if value is not None else default),
                _canonical_bool=lambda *_: False,
                _cap_current=lambda value: value,
                paused_done_resume_is_authorized=lambda *_: False,
                MIN_START_TEMP=10.0,
                MIN_INPUT_VOLTAGE=45.0,
                time=types.SimpleNamespace(time=lambda: now),
                log_event=lambda *_args: None,
            )

            asyncio.run(toggle_operator_pause(host))
            self.assertEqual(events, ["verified_on", "shift"])
            self.assertFalse(state.active())

            state.started_at = now - 10.0
            controller.current_stage = "SAFE_WAIT"
            live["switch"] = "off"
            events.clear()
            port.on_calls = 0
            asyncio.run(toggle_operator_pause(host))
            self.assertEqual(port.on_calls, 0)
            self.assertEqual(events, ["shift"])


if __name__ == "__main__":
    unittest.main()
