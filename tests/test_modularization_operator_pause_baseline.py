"""Current-owner contracts for operator pause/resume."""

import asyncio
import ast
import tempfile
import time
import types
import unittest
from pathlib import Path

from application.operator_pause_use_case import toggle_operator_pause
from runtime.charge.controller_state import shift_active_clocks
from runtime.operator.pause_state import OperatorPauseState


class _AsyncLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class FakePort:
    def __init__(self, live, *, off=True, on=True):
        self.live = live
        self.off_result = off
        self.on_result = on
        self.off_calls = 0
        self.on_calls = 0
        self.program_calls = []
        self._guard_owner_lock = _AsyncLock()

    async def read_live(self):
        return dict(self.live)

    async def request_verified_off(self):
        self.off_calls += 1
        if self.off_result:
            self.live["switch"] = "off"
        return self.off_result

    async def request_verified_on(self):
        self.on_calls += 1
        if self.on_result:
            self.live["switch"] = "on"
        return self.on_result

    async def program_voltage(self, value):
        self.program_calls.append(("voltage", value))
        return True

    async def program_current(self, value):
        self.program_calls.append(("current", value))
        return True


class FakeController:
    is_active = True
    current_stage = "CV"
    STAGE_SAFE_WAIT = "SAFE_WAIT"

    def __init__(self):
        self.saved = []
        self.stage_start_time = 100.0
        self.total_start_time = 200.0
        self._main_sample_evidence = types.SimpleNamespace(shifts=[])
        self._main_sample_evidence.shift_clock = self._main_sample_evidence.shifts.append

    def _save_session(self, *values):
        self.saved.append(values)

    def _get_target_v_i(self, _temperature):
        return (14.7, 0.3)

    def shift_active_clocks(self, seconds):
        shift_active_clocks(self, seconds)


class OperatorPauseBaselineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pause_file = str(Path(self.tmp.name) / "pause.json")
        self.state = OperatorPauseState()
        self.controller = FakeController()
        self.live = {
            "switch": "on",
            "battery_voltage": 14.6,
            "current": 0.4,
            "ah": 12.0,
            "temp_ext": 25.0,
            "input_voltage": 60.0,
        }
        self.port = FakePort(self.live)
        self.now = time.time()
        self.host = types.SimpleNamespace(
            hass=types.SimpleNamespace(get_all_live=self._get_live),
            charge_controller=self.controller,
            _operator_pause_state=self.state,
            _operator_pause_active=self.state.active,
            _runtime_execution_port=lambda: self.port,
            _save_operator_pause_state=lambda: self.state.save(self.pause_file),
            _clear_operator_pause=lambda: self.state.clear(self.pause_file),
            _safe_float=lambda value, default=0.0: float(value if value is not None else default),
            _canonical_bool=lambda *_: False,
            _cap_current=lambda value: value,
            paused_done_resume_is_authorized=lambda *_: False,
            MIN_START_TEMP=10.0,
            MIN_INPUT_VOLTAGE=45.0,
            time=types.SimpleNamespace(time=lambda: self.now),
            log_event=lambda *_args: None,
        )

    def tearDown(self):
        self.tmp.cleanup()

    async def _get_live(self):
        return dict(self.live)

    def test_one_field_sidecar_round_trip_and_clear(self):
        self.state.started_at = 1234.5
        self.state.save(self.pause_file)
        loaded = OperatorPauseState.load(self.pause_file)
        self.assertEqual(loaded.started_at, 1234.5)
        loaded.clear(self.pause_file)
        self.assertFalse(Path(self.pause_file).exists())

    def test_missing_invalid_nonmapping_and_negative_are_unpaused(self):
        self.assertFalse(OperatorPauseState.load(self.pause_file).active())
        for content in ("{bad", "[]", '{"started_at": -5}'):
            Path(self.pause_file).write_text(content, encoding="utf-8")
            self.assertFalse(OperatorPauseState.load(self.pause_file).active())

    def test_pause_persists_only_after_verified_output_off(self):
        self.port.off_result = False
        result = asyncio.run(toggle_operator_pause(self.host))
        self.assertIn("не подтверждён OFF", result)
        self.assertFalse(self.state.active())
        self.assertFalse(Path(self.pause_file).exists())
        self.assertEqual(self.controller.saved, [])

    def test_failed_resume_on_does_not_clear_or_shift(self):
        self.state.started_at = self.now - 10.0
        self.live["switch"] = "off"
        self.port.on_result = False
        paused_at = self.state.started_at
        result = asyncio.run(toggle_operator_pause(self.host))
        self.assertIn("включение не подтверждено", result)
        self.assertEqual(self.state.started_at, paused_at)
        self.assertEqual(self.controller._main_sample_evidence.shifts, [])
        self.assertEqual(self.controller.stage_start_time, 100.0)

    def test_verified_resume_shifts_once_then_clears(self):
        self.state.started_at = self.now - 10.0
        self.live["switch"] = "off"
        result = asyncio.run(toggle_operator_pause(self.host))
        self.assertIn("заряд продолжен", result)
        self.assertFalse(self.state.active())
        self.assertEqual(self.controller._main_sample_evidence.shifts, [10.0])
        self.assertEqual(self.controller.stage_start_time, 110.0)

    def test_safe_wait_shifts_without_requesting_output_on(self):
        self.state.started_at = self.now - 10.0
        self.live["switch"] = "off"
        self.controller.current_stage = "SAFE_WAIT"
        result = asyncio.run(toggle_operator_pause(self.host))
        self.assertIn("ожидание продолжает контролироваться", result)
        self.assertEqual(self.port.on_calls, 0)
        self.assertEqual(self.controller._main_sample_evidence.shifts, [10.0])
        self.assertFalse(self.state.active())

    def test_emergency_stop_contract_is_not_redefined_by_pause(self):
        source = Path(__file__).resolve().parents[1] / "application" / "operator_pause_use_case.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        self.assertNotIn("_emergency_stop", names)
        self.assertNotIn("_trip_safety_guard", names)


if __name__ == "__main__":
    unittest.main()
