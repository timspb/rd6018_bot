"""Fake-only behavior contract for the Manual observer use case."""

import ast
import unittest
from enum import Enum
from pathlib import Path
from types import SimpleNamespace

from application.manual_observer_use_case import (
    MANUAL_COOLING_PAUSE_C,
    MANUAL_COOLING_RESUME_C,
    MANUAL_TEMP_CRITICAL_C,
    observe_manual_session_once,
)
from runtime.safety.thermal_variables import (
    BATTERY_TEMP_CRITICAL_C,
    BATTERY_TEMP_PAUSE_C,
    MANUAL_COOLING_RESUME_C as MANUAL_COOLING_RESUME_THRESHOLD_C,
)


def _load_session_state():
    source_path = Path(__file__).resolve().parents[1] / "manual_mode.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    state_enum = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ManualSessionState"
    )
    isolated = ast.Module(body=[state_enum], type_ignores=[])
    namespace = {"Enum": Enum}
    exec(compile(ast.fix_missing_locations(isolated), str(source_path), "exec"), namespace)
    return namespace


_SOURCE_GLOBALS = _load_session_state()
ManualSessionState = _SOURCE_GLOBALS["ManualSessionState"]


class FakeRequest:
    def __init__(self, operation_mode="main"):
        self.operation_mode = operation_mode
        self.profile = None


class FakeExecutionPort:
    def __init__(self, hass):
        self.hass = hass
        self.read_calls = 0
        self.disable_calls = []
        self.enable_calls = []

    async def read_live(self):
        self.read_calls += 1
        return await self.hass.get_all_live()

    async def disable(self, *args, **kwargs):
        self.disable_calls.append((args, kwargs))
        return SimpleNamespace(verified=True, reason="")

    async def enable(self, *args, **kwargs):
        self.enable_calls.append((args, kwargs))
        return SimpleNamespace(verified=True, reason="")


class FakeHass:
    def __init__(self, live=None):
        self.live = live or {"temp_ext": 20.0, "battery_voltage": 14.0, "current": 1.0}
        self.reads = 0

    async def get_all_live(self):
        self.reads += 1
        return dict(self.live)


class FakeSession:
    """Only the attributes and collaborators read by source observe_once."""

    def __init__(self, *, state=ManualSessionState.ACTIVE, request=None, live=None):
        self.state = state
        self.request = request if request is not None else FakeRequest()
        self.app = SimpleNamespace(hass=FakeHass(live))
        self.execution_port = FakeExecutionPort(self.app.hass)
        self.started_at = 1.0
        self.finish_hold_started_at = None
        self.persist_calls = 0
        self.stop_calls = []
        self.cooling_calls = 0
        self.resume_calls = 0
        self.threshold_calls = 0
        self.main_tail_calls = 0
        self.mix_hold_calls = 0
        self.delta_calls = 0
        self.advance_calls = 0
        self.threshold_result = None
        self.main_tail_result = None
        self.mix_hold_result = None
        self.delta_result = None
        self.active_elapsed_s = 0.0

    @property
    def is_active(self):
        return self.state in {ManualSessionState.ACTIVE, ManualSessionState.COOLING}

    def _persist(self):
        self.persist_calls += 1

    async def stop(self, reason):
        self.stop_calls.append(reason)
        intent = SimpleNamespace(name="fake-stop")
        await self.execution_port.disable(intent, reason=reason)

    async def _enter_cooling(self):
        self.cooling_calls += 1
        await self.execution_port.disable(SimpleNamespace(name="fake-cooling"), reason="thermal_pause")
        self.state = ManualSessionState.COOLING
        self._persist()

    async def _resume_after_cooling(self):
        self.resume_calls += 1
        await self.execution_port.enable(SimpleNamespace(name="fake-resume"))
        self.state = ManualSessionState.ACTIVE
        self._persist()

    def _threshold_reason(self, voltage, current):
        self.threshold_calls += 1
        return self.threshold_result

    def _main_tail_reason(self, live):
        self.main_tail_calls += 1
        return self.main_tail_result

    async def _advance_profile_to_mix(self):
        self.advance_calls += 1

    def _mix_hold_reason(self, *, now):
        self.mix_hold_calls += 1
        return self.mix_hold_result

    def _delta_reason(self, sample, *, now):
        self.delta_calls += 1
        return self.delta_result


async def _observe(session):
    await observe_manual_session_once(session)


class ManualObserverContractTests(unittest.IsolatedAsyncioTestCase):
    def test_manual_thermal_thresholds_use_the_canonical_safety_variables(self):
        self.assertEqual(MANUAL_COOLING_PAUSE_C, float(BATTERY_TEMP_PAUSE_C.default))
        self.assertEqual(MANUAL_COOLING_RESUME_C, float(MANUAL_COOLING_RESUME_THRESHOLD_C.default))
        self.assertEqual(MANUAL_TEMP_CRITICAL_C, float(BATTERY_TEMP_CRITICAL_C.default))
        self.assertEqual(
            (
                MANUAL_COOLING_PAUSE_C,
                MANUAL_COOLING_RESUME_C,
                MANUAL_TEMP_CRITICAL_C,
            ),
            (40.0, 35.0, 45.0),
        )
        self.assertEqual(MANUAL_COOLING_RESUME_THRESHOLD_C.key, "safety.thermal.manual_cooling_resume_c")
        self.assertEqual(MANUAL_COOLING_RESUME_THRESHOLD_C.owner, "runtime.safety.thermal")

    def test_observer_uses_execution_port_read_boundary(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "application"
            / "manual_observer_use_case.py"
        ).read_text(encoding="utf-8")
        self.assertIn("self.execution_port.read_live()", source)
        self.assertNotIn("self.app.hass.get_all_live()", source)

    async def test_inactive_or_missing_request_does_not_read_or_act(self):
        for session in (
            FakeSession(state=ManualSessionState.IDLE),
            FakeSession(),
        ):
            if session.state is ManualSessionState.ACTIVE:
                session.request = None
            await _observe(session)
            self.assertEqual(session.execution_port.read_calls, 0)
            self.assertEqual(session.stop_calls, [])
            self.assertEqual(session.execution_port.disable_calls, [])

    async def test_missing_temperature_does_not_act(self):
        session = FakeSession(live={"battery_voltage": 14.0, "current": 1.0})
        await _observe(session)
        self.assertEqual(session.execution_port.read_calls, 1)
        self.assertEqual(session.stop_calls, [])
        self.assertEqual(session.execution_port.disable_calls, [])

    async def test_critical_temperature_stops_with_current_reason(self):
        session = FakeSession(live={"temp_ext": 45.0, "battery_voltage": 14.0, "current": 1.0})
        await _observe(session)
        self.assertEqual(session.stop_calls, ["manual_critical_battery_temperature"])
        self.assertEqual(len(session.execution_port.disable_calls), 1)
        self.assertEqual(session.threshold_calls, 0)

    async def test_cooling_resumes_at_or_below_resume_threshold(self):
        session = FakeSession(state=ManualSessionState.COOLING, live={"temp_ext": 35.0})
        await _observe(session)
        self.assertEqual(session.resume_calls, 1)
        self.assertEqual(len(session.execution_port.enable_calls), 1)
        self.assertEqual(session.cooling_calls, 0)
        self.assertEqual(session.threshold_calls, 0)

    async def test_active_session_enters_cooling_at_pause_threshold(self):
        session = FakeSession(live={"temp_ext": 40.0})
        await _observe(session)
        self.assertEqual(session.cooling_calls, 1)
        self.assertEqual(len(session.execution_port.disable_calls), 1)
        self.assertEqual(session.threshold_calls, 0)

    async def test_missing_voltage_or_current_does_not_stop(self):
        for live in ({"temp_ext": 20.0, "current": 1.0}, {"temp_ext": 20.0, "battery_voltage": 14.0}):
            session = FakeSession(live=live)
            await _observe(session)
            self.assertEqual(session.stop_calls, [])
            self.assertEqual(session.threshold_calls, 0)

    async def test_missing_voltage_or_current_skips_hold_and_delta(self):
        for live in ({"temp_ext": 20.0, "current": 1.0}, {"temp_ext": 20.0, "battery_voltage": 14.0}):
            session = FakeSession(request=FakeRequest(operation_mode="mix"), live=live)
            session.finish_hold_started_at = 1.0
            await _observe(session)
            self.assertEqual(session.mix_hold_calls, 0)
            self.assertEqual(session.delta_calls, 0)

    async def test_unknown_regulation_does_not_preempt_started_hold_evaluation(self):
        session = FakeSession(
            request=FakeRequest(operation_mode="mix"),
            live={"temp_ext": 20.0, "battery_voltage": 14.0, "current": 1.0, "regulation_code": 9},
        )
        session.finish_hold_started_at = 1.0
        session.mix_hold_result = "manual_mix_delta_hold_complete"
        await _observe(session)
        self.assertEqual(session.mix_hold_calls, 1)
        self.assertEqual(session.delta_calls, 0)
        self.assertEqual(session.stop_calls, ["manual_mix_delta_hold_complete"])
        self.assertEqual(len(session.execution_port.disable_calls), 1)

    async def test_threshold_reason_precedes_tail_hold_and_delta(self):
        session = FakeSession()
        session.threshold_result = "manual_time_limit"
        session.main_tail_result = "manual_main_cv_imin"
        session.mix_hold_result = "manual_mix_delta_hold_complete"
        session.delta_result = "manual_delta_confirmed"
        await _observe(session)
        self.assertEqual(session.stop_calls, ["manual_time_limit"])
        self.assertEqual(session.main_tail_calls, 0)
        self.assertEqual(session.mix_hold_calls, 0)
        self.assertEqual(session.delta_calls, 0)

    async def test_main_tail_reason_precedes_mix_hold_and_delta(self):
        session = FakeSession()
        session.main_tail_result = "manual_main_cv_imin"
        session.mix_hold_result = "manual_mix_delta_hold_complete"
        session.delta_result = "manual_delta_confirmed"
        await _observe(session)
        self.assertEqual(session.stop_calls, ["manual_main_cv_imin"])
        self.assertEqual(session.mix_hold_calls, 0)
        self.assertEqual(session.delta_calls, 0)

    async def test_main_to_mix_effect_preempts_later_hold_and_delta(self):
        session = FakeSession()
        session.main_tail_result = "manual_main_to_mix"
        await _observe(session)
        self.assertEqual(session.advance_calls, 1)
        self.assertEqual(session.mix_hold_calls, 0)
        self.assertEqual(session.delta_calls, 0)
        self.assertEqual(session.stop_calls, [])

    async def test_confirmed_delta_starts_and_persists_hold_without_immediate_stop(self):
        session = FakeSession(request=FakeRequest(operation_mode="mix"))
        session.delta_result = "manual_delta_confirmed"
        await _observe(session)
        self.assertIsNotNone(session.finish_hold_started_at)
        self.assertEqual(session.persist_calls, 1)
        self.assertEqual(session.stop_calls, [])
        self.assertEqual(session.execution_port.disable_calls, [])

    async def test_terminal_reason_stops_once_with_original_text(self):
        session = FakeSession()
        session.threshold_result = "manual_voltage_ge"
        await _observe(session)
        self.assertEqual(session.stop_calls, ["manual_voltage_ge"])
        self.assertEqual(len(session.execution_port.disable_calls), 1)


if __name__ == "__main__":
    unittest.main()
