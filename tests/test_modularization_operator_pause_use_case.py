"""Fake-only tests for the extracted operator pause application use case."""

import ast
import asyncio
import sys
import time
import types
import unittest
from pathlib import Path

from application.operator_pause_use_case import toggle_operator_pause
from application.guard_execution_owner_lock import GuardExecutionOwnerLock


ROOT = Path(__file__).resolve().parents[1]


class Port:
    def __init__(self, host):
        self.host = host
        self._guard_owner_lock = GuardExecutionOwnerLock()
        self.on_result = True
        self.events = []
        self.reads = 0
        self.cancel_at = None
        self.voltage_result = True
        self.current_result = True
        self.cleanup_trace = []
        self.read_values = {}
        self.emergency_error = False
        self.emergency_result = True

    def _assert_owner_lock(self):
        lock = self._guard_owner_lock
        if not lock.locked() or lock.owner_task is not asyncio.current_task():
            raise AssertionError("Operator Pause action escaped the app execution transaction")

    async def read_live(self):
        self.reads += 1
        if self.events and self.events[-1] == "emergency_off":
            self.cleanup_trace.append("fresh_readback")
        if self.cancel_at == f"read{self.reads}":
            raise asyncio.CancelledError
        result = dict(self.host.live)
        result.update(self.read_values.get(self.reads, {}))
        if self.reads in self.read_values and "switch" in self.read_values[self.reads]:
            value = self.read_values[self.reads]["switch"]
            if value is ...:
                result.pop("switch", None)
            else:
                result["switch"] = value
        return result

    async def request_verified_off(self):
        self._assert_owner_lock()
        self.events.append("off")
        if self.host.off_allowed:
            self.host.live["switch"] = "off"
        if self.cancel_at == "off":
            raise asyncio.CancelledError
        return self.host.off_allowed

    async def request_emergency_off(self):
        if not self._guard_owner_lock.locked():
            raise AssertionError("preemptive emergency OFF must run during the owner transaction")
        if self._guard_owner_lock.owner_task is asyncio.current_task():
            raise AssertionError("emergency OFF must not wait for or re-enter the owner lock")
        self.events.append("emergency_off")
        self.cleanup_trace.append("emergency_off")
        self.host.live["switch"] = "off"
        if self.emergency_error:
            raise RuntimeError("edge may have received emergency OFF")
        return self.emergency_result

    async def request_verified_on(self):
        self._assert_owner_lock()
        self.events.append("on")
        if self.on_result:
            self.host.live["switch"] = "on"
        if self.cancel_at == "on":
            raise asyncio.CancelledError
        return self.on_result

    async def program_voltage(self, _value):
        self._assert_owner_lock()
        self.events.append("voltage")
        if self.cancel_at == "voltage":
            raise asyncio.CancelledError
        return self.voltage_result

    async def program_current(self, _value):
        self._assert_owner_lock()
        self.events.append("current")
        if self.cancel_at == "current":
            raise asyncio.CancelledError
        return self.current_result


class Controller:
    is_active = True
    current_stage = "CV"
    STAGE_SAFE_WAIT = "SAFE_WAIT"

    def __init__(self):
        self.saved = 0
        self.restored = 0
        self.shifts = []
        self.on_shift = None

    def shift_active_clocks(self, seconds):
        self.shifts.append(seconds)
        if self.on_shift:
            self.on_shift()

    def _save_session(self, *_args):
        self.saved += 1

    def _get_target_v_i(self, _temp):
        return 14.7, 0.3


class Host:
    MIN_START_TEMP = 10.0
    MIN_INPUT_VOLTAGE = 45.0

    def __init__(self, output="off", paused=None):
        self.live = {"switch": output, "battery_voltage": 14.6, "current": 0.4,
                     "ah": 12.0, "temp_ext": 25.0, "input_voltage": 60.0}
        self.charge_controller = Controller()
        self._operator_pause_state = types.SimpleNamespace(started_at=paused)
        self.now = 200.0
        self.time = types.SimpleNamespace(time=lambda: self.now)
        self.port = Port(self)
        self.off_allowed = True
        self.saved_state = 0
        self.clears = 0
        self.events = []
        self.hass = types.SimpleNamespace(get_all_live=self._live)
        self.sys = types.SimpleNamespace(modules={"runtime.production_runtime": self})

    async def _live(self):
        return dict(self.live)

    def _operator_pause_active(self):
        return self._operator_pause_state.started_at is not None

    def _runtime_execution_port(self):
        return self.port

    def _safe_float(self, value, default=0.0):
        return float(value if value is not None else default)

    def _save_operator_pause_state(self):
        self.saved_state += 1

    def _clear_operator_pause(self):
        self.clears += 1
        self._operator_pause_state.started_at = None
        return True

    def _cap_current(self, value):
        return value

    def _canonical_bool(self, _live, _key):
        return False

    def paused_done_resume_is_authorized(self, *_args):
        return False

    def log_event(self, *_args):
        self.events.append(_args[-1])


class OperatorPauseUseCaseTests(unittest.TestCase):
    def run_case(self, host):
        return asyncio.run(toggle_operator_pause(host))

    def test_pause_telemetry_reads_use_execution_port_not_raw_hass(self):
        host = Host(output="off")
        host.hass.get_all_live = lambda: (_ for _ in ()).throw(
            AssertionError("operator pause must not bypass ExecutionPort")
        )
        result = self.run_case(host)
        self.assertEqual(result, "Пауза включена · Output OFF подтверждён")
        self.assertEqual(host.port.reads, 2)

    def test_source_uses_only_execution_port_for_live_telemetry(self):
        source = (ROOT / "application" / "operator_pause_use_case.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("port.read_live()"), 4)
        self.assertNotIn("host.hass.get_all_live()", source)
        self.assertIn("async with lock:", source)
        self.assertIn("_toggle_operator_pause_locked(host, port)", source)

    def test_pause_transaction_holds_owner_lock_against_interleaving_normal_work(self):
        host = Host(output="off", paused=190.0)
        lock = host.port._guard_owner_lock
        entered = asyncio.Event()
        release = asyncio.Event()
        original_read = host.port.read_live

        async def blocked_read():
            if host.port.reads == 0:
                entered.set()
                await release.wait()
            return await original_read()

        host.port.read_live = blocked_read

        async def scenario():
            pause_task = asyncio.create_task(toggle_operator_pause(host))
            await asyncio.wait_for(entered.wait(), 1)
            competitor = asyncio.create_task(lock.run(lambda: asyncio.sleep(0, result="competitor")))
            await asyncio.sleep(0)
            self.assertFalse(competitor.done())
            release.set()
            result = await asyncio.wait_for(pause_task, 1)
            self.assertEqual(await asyncio.wait_for(competitor, 1), "competitor")
            return result

        result = asyncio.run(scenario())
        self.assertEqual(result, "Пауза снята · заряд продолжен")
        self.assertEqual(host.port.events, ["voltage", "current", "on"])
        self.assertEqual(host.charge_controller.shifts, [10.0])
        self.assertFalse(lock.locked())

    def test_pause_saves_only_after_verified_off_readback(self):
        host = Host(output="on")
        result = self.run_case(host)
        self.assertEqual(result, "Пауза включена · Output OFF подтверждён")
        self.assertEqual(host.port.events, ["off"])
        self.assertEqual(host.saved_state, 1)
        self.assertEqual(host.charge_controller.saved, 1)
        self.assertIsNotNone(host._operator_pause_state.started_at)

    def test_canonical_off_values_are_accepted_for_pause_initial_and_readback(self):
        for value in (False, 0, "off", "false", "no", "0"):
            with self.subTest(value=value, position="initial"):
                host = Host(output=value)
                result = self.run_case(host)
                self.assertEqual(result, "Пауза включена · Output OFF подтверждён")
                self.assertEqual(host.port.events, [])
                self.assertEqual(host.port.reads, 2)
                self.assertEqual(host.saved_state, 1)
            with self.subTest(value=value, position="post_off"):
                host = Host(output="on")
                host.port.read_values[2] = {"switch": value}
                result = self.run_case(host)
                self.assertEqual(result, "Пауза включена · Output OFF подтверждён")
                self.assertEqual(host.port.events, ["off"])
                self.assertEqual(host.saved_state, 1)

    def test_canonical_off_values_are_accepted_for_resume_initial_and_post_off_readback(self):
        for value in (False, 0, "off", "false", "no", "0"):
            with self.subTest(value=value, position="initial"):
                host = Host(output=value, paused=190.0)
                result = self.run_case(host)
                self.assertEqual(result, "Пауза снята · заряд продолжен")
                self.assertEqual(host.port.events, ["voltage", "current", "on"])
            with self.subTest(value=value, position="post_off"):
                host = Host(output="on", paused=190.0)
                host.port.read_values[2] = {"switch": value}
                result = self.run_case(host)
                self.assertEqual(result, "Пауза снята · заряд продолжен")
                self.assertEqual(host.port.events, ["off", "voltage", "current", "on"])

    def test_none_unknown_empty_and_malformed_switch_are_not_off(self):
        for value in (None, "unknown", "", " malformed ", {}, [], True, 2):
            with self.subTest(value=value):
                host = Host(output=value)
                host.off_allowed = False
                result = self.run_case(host)
                self.assertEqual(result, "Пауза не включена: Output не подтверждён OFF")
                self.assertEqual(host.port.events, ["off"])
                self.assertEqual(host.saved_state, 0)
                self.assertEqual(host.charge_controller.saved, 0)
                self.assertEqual(host.events, [])

    def test_unknown_initial_pause_state_requests_off_and_requires_positive_readback(self):
        for value in (None, "", "unknown", " malformed ", ...):
            with self.subTest(value=value):
                host = Host(output=value)
                if value is ...:
                    host.live.pop("switch")
                host.off_allowed = False
                result = self.run_case(host)
                self.assertEqual(result, "Пауза не включена: Output не подтверждён OFF")
                self.assertEqual(host.port.events, ["off"])
                self.assertEqual(host.saved_state, 0)
                self.assertEqual(host.charge_controller.saved, 0)
                self.assertEqual(host.events, [])
                self.assertIsNone(host._operator_pause_state.started_at)
                self.assertFalse(host.port._guard_owner_lock.locked())

    def test_unknown_post_off_pause_readback_blocks_commit(self):
        for value in (None, "", "unknown", ...):
            with self.subTest(value=value):
                host = Host(output="on")
                host.port.read_values[2] = {"switch": value}
                result = self.run_case(host)
                self.assertEqual(result, "Пауза не включена: Output не подтверждён OFF")
                self.assertEqual(host.saved_state, 0)
                self.assertEqual(host.charge_controller.saved, 0)
                self.assertEqual(host.events, [])
                self.assertIsNone(host._operator_pause_state.started_at)
                self.assertFalse(host.port._guard_owner_lock.locked())

    def test_unknown_initial_resume_state_requires_off_readback_before_writes(self):
        for value in (None, "", "unknown", ...):
            with self.subTest(value=value):
                host = Host(output=value, paused=190.0)
                if value is ...:
                    host.live.pop("switch")
                host.off_allowed = False
                result = self.run_case(host)
                self.assertEqual(result, "Продолжение заблокировано: Output не подтверждён OFF")
                self.assertEqual(host.port.events, ["off"])
                self.assertEqual(host._operator_pause_state.started_at, 190.0)
                self.assertEqual(host.charge_controller.shifts, [])
                self.assertEqual(host.events, [])
                self.assertFalse(host.port._guard_owner_lock.locked())

    def test_unknown_post_off_resume_readback_blocks_programming(self):
        for value in (None, "", "unknown", ...):
            with self.subTest(value=value):
                host = Host(output="on", paused=190.0)
                host.port.read_values[2] = {"switch": value}
                result = self.run_case(host)
                self.assertEqual(result, "Продолжение заблокировано: Output не подтверждён OFF")
                self.assertEqual(host.port.events, ["off"])
                self.assertEqual(host._operator_pause_state.started_at, 190.0)
                self.assertEqual(host.charge_controller.shifts, [])
                self.assertEqual(host.events, [])
                self.assertFalse(host.port._guard_owner_lock.locked())

    def test_resume_unknown_initial_state_can_continue_only_after_fresh_off(self):
        host = Host(output="unknown", paused=190.0)
        result = self.run_case(host)
        self.assertEqual(result, "Пауза снята · заряд продолжен")
        self.assertEqual(host.port.events, ["off", "voltage", "current", "on"])
        self.assertEqual(host.port.reads, 2)
        self.assertEqual(host.charge_controller.shifts, [10.0])
        self.assertFalse(host.port._guard_owner_lock.locked())

    def test_denied_off_leaves_pause_unarmed(self):
        host = Host(output="on")
        host.off_allowed = False
        result = self.run_case(host)
        self.assertEqual(result, "Пауза не включена: Output не подтверждён OFF")
        self.assertIsNone(host._operator_pause_state.started_at)
        self.assertEqual(host.saved_state, 0)

    def test_failed_verified_on_keeps_pause_and_does_not_shift(self):
        host = Host(paused=190.0)
        host.port.on_result = False
        result = self.run_case(host)
        self.assertEqual(result, "Продолжение заблокировано: безопасное включение не подтверждено")
        self.assertEqual(host.port.events, ["voltage", "current", "on"])
        self.assertEqual(host.charge_controller.shifts, [])
        self.assertEqual(host._operator_pause_state.started_at, 190.0)
        self.assertEqual(host.clears, 0)

    def test_rejected_voltage_or_current_never_requests_output_on(self):
        for field in ("voltage_result", "current_result"):
            with self.subTest(field=field):
                host = Host(paused=190.0)
                setattr(host.port, field, False)
                result = self.run_case(host)
                self.assertIn("уставки", result)
                self.assertNotIn("on", host.port.events)
                self.assertEqual(host._operator_pause_state.started_at, 190.0)
                self.assertEqual(host.charge_controller.shifts, [])

    def test_cancelled_await_boundaries_follow_pause_resume_compensation(self):
        cases = (
            ("pause_initial_read", Host(output="off"), "read1", [], None),
            ("pause_off", Host(output="on"), "off", ["off", "emergency_off"], 200.0),
            ("pause_readback", Host(output="on"), "read2", ["off", "emergency_off"], 200.0),
            ("resume_initial_read", Host(paused=190.0), "read1", [], 190.0),
            ("resume_voltage", Host(paused=190.0), "voltage", ["voltage"], 190.0),
            ("resume_current", Host(paused=190.0), "current", ["voltage", "current"], 190.0),
            ("resume_on", Host(paused=190.0), "on", ["voltage", "current", "on", "emergency_off"], 190.0),
        )
        for name, host, boundary, expected, pause_value in cases:
            with self.subTest(name=name):
                host.port.cancel_at = boundary
                with self.assertRaises(asyncio.CancelledError):
                    self.run_case(host)
                self.assertEqual(host.port.events, expected)
                self.assertEqual(host._operator_pause_state.started_at, pause_value)
                self.assertEqual(host.charge_controller.shifts, [])
                if "emergency_off" in expected:
                    self.assertEqual(host.port.cleanup_trace, ["emergency_off", "fresh_readback"])
                if name.startswith("pause_") and name != "pause_initial_read":
                    self.assertEqual(host.charge_controller.saved, 1)
                    self.assertEqual(host.events, ["OPERATOR_PAUSE_ON"])
                self.assertFalse(host.port._guard_owner_lock.locked())

    def test_cancelled_pause_unknown_emergency_readback_does_not_commit(self):
        host = Host(output="on")
        host.port.cancel_at = "off"
        host.port.read_values[2] = {"switch": "unknown"}
        with self.assertRaises(asyncio.CancelledError):
            self.run_case(host)
        self.assertEqual(host._operator_pause_state.started_at, None)
        self.assertEqual(host.saved_state, 0)
        self.assertEqual(host.charge_controller.saved, 0)
        self.assertEqual(host.events, [])
        self.assertEqual(host.port.cleanup_trace, ["emergency_off", "fresh_readback"])
        self.assertFalse(host.port._guard_owner_lock.locked())

    def test_cancelled_pause_reads_after_emergency_off_exception_and_commits_only_on_off(self):
        host = Host(output="on")
        host.port.cancel_at = "off"
        host.port.emergency_error = True
        with self.assertRaises(asyncio.CancelledError):
            self.run_case(host)
        self.assertEqual(host.port.reads, 2)
        self.assertEqual(host.port.cleanup_trace, ["emergency_off", "fresh_readback"])
        self.assertEqual(host.saved_state, 1)
        self.assertEqual(host.charge_controller.saved, 1)
        self.assertEqual(host.events, ["OPERATOR_PAUSE_ON"])
        self.assertIsNotNone(host._operator_pause_state.started_at)
        self.assertFalse(host.port._guard_owner_lock.locked())

    def test_cancelled_emergency_cleanup_does_not_swallow_cancelled_error(self):
        host = Host(output="on")
        host.port.cancel_at = "off"
        async def cancelled_emergency_off():
            host.port.events.append("emergency_off")
            host.port.cleanup_trace.append("emergency_off")
            raise asyncio.CancelledError
        host.port.request_emergency_off = cancelled_emergency_off
        with self.assertRaises(asyncio.CancelledError):
            self.run_case(host)
        self.assertEqual(host.port.cleanup_trace, ["emergency_off"])
        self.assertEqual(host.saved_state, 0)
        self.assertEqual(host.events, [])
        self.assertFalse(host.port._guard_owner_lock.locked())

    def test_cancelled_pause_reads_after_emergency_off_returns_false(self):
        host = Host(output="on")
        host.port.cancel_at = "off"
        host.port.emergency_result = False
        with self.assertRaises(asyncio.CancelledError):
            self.run_case(host)
        self.assertEqual(host.port.reads, 2)
        self.assertEqual(host.port.cleanup_trace, ["emergency_off", "fresh_readback"])
        self.assertEqual(host.saved_state, 1)
        self.assertEqual(host.events, ["OPERATOR_PAUSE_ON"])
        self.assertFalse(host.port._guard_owner_lock.locked())

    def test_cancel_during_unexpected_on_containment_uses_emergency_off(self):
        host = Host(output="on", paused=190.0)
        host.port.cancel_at = "off"
        with self.assertRaises(asyncio.CancelledError):
            self.run_case(host)
        self.assertEqual(host.port.events, ["off", "emergency_off"])
        self.assertEqual(host.port.cleanup_trace, ["emergency_off", "fresh_readback"])
        self.assertEqual(host._operator_pause_state.started_at, 190.0)
        self.assertFalse(host.port._guard_owner_lock.locked())

    def test_cancel_during_unexpected_on_readback_uses_emergency_off(self):
        host = Host(output="on", paused=190.0)
        host.port.cancel_at = "read2"
        with self.assertRaises(asyncio.CancelledError):
            self.run_case(host)
        self.assertEqual(host.port.events, ["off", "emergency_off"])
        self.assertEqual(host.port.cleanup_trace, ["emergency_off", "fresh_readback"])
        self.assertEqual(host._operator_pause_state.started_at, 190.0)
        self.assertFalse(host.port._guard_owner_lock.locked())

    def test_failed_pause_save_restores_memory_and_does_not_emit_event(self):
        host = Host(output="off")
        prior = 180.0
        host._operator_pause_state.started_at = prior
        host._operator_pause_active = lambda: False
        host._save_operator_pause_state = lambda: (_ for _ in ()).throw(OSError("disk"))
        result = self.run_case(host)
        self.assertEqual(result, "Пауза не включена: состояние не сохранено")
        self.assertEqual(host._operator_pause_state.started_at, prior)
        self.assertEqual(host.events, [])

    def test_failed_resume_clear_keeps_pause_and_clock_and_contains_output(self):
        host = Host(paused=190.0)
        host._clear_operator_pause = lambda: (_ for _ in ()).throw(OSError("disk"))
        result = self.run_case(host)
        self.assertEqual(result, "Продолжение заблокировано: пауза не удалена")
        self.assertEqual(host._operator_pause_state.started_at, 190.0)
        self.assertEqual(host.charge_controller.shifts, [])
        self.assertEqual(host.port.events, ["voltage", "current", "on", "emergency_off"])

    def test_verified_on_shifts_once_after_on_then_clears(self):
        host = Host(paused=190.0)
        host.charge_controller.on_shift = lambda: self.assertEqual(host.port.events[-1], "on")
        result = self.run_case(host)
        self.assertEqual(result, "Пауза снята · заряд продолжен")
        self.assertEqual(host.charge_controller.shifts, [10.0])
        self.assertEqual(host.clears, 1)

    def test_safe_wait_shifts_once_without_requesting_on(self):
        host = Host(paused=190.0)
        host.charge_controller.current_stage = "SAFE_WAIT"
        result = self.run_case(host)
        self.assertEqual(result, "Пауза снята · ожидание продолжает контролироваться")
        self.assertEqual(host.port.events, [])
        self.assertEqual(host.charge_controller.shifts, [10.0])
        self.assertEqual(host.clears, 1)

    def test_permission_denial_returns_before_use_case_call(self):
        source = (ROOT / "runtime" / "production_runtime.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        fn = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                  and node.name == "_operator_pause_toggle")
        calls = [node for node in ast.walk(fn) if isinstance(node, ast.Call)]
        usecase = [node for node in calls if isinstance(node.func, ast.Name)
                   and node.func.id == "toggle_operator_pause"]
        self.assertEqual(len(usecase), 1)
        deny = next(node for node in ast.walk(fn) if isinstance(node, ast.If)
                    and any(isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                            and call.func.id == "_is_action_allowed" for call in ast.walk(node.test)))
        self.assertTrue(any(isinstance(node, ast.Return) for node in ast.walk(deny))
                        if isinstance(deny, ast.If) else False)
        self.assertLess(fn.body.index(deny), fn.body.index(next(
            node for node in fn.body if isinstance(node, ast.Return)
            and any(isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                    and call.func.id == "toggle_operator_pause" for call in ast.walk(node.value)))))


if __name__ == "__main__":
    unittest.main()
