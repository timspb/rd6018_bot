"""P3-2 typed effect and source ownership checks."""

import ast
from pathlib import Path
import unittest

from charge_controller import ManagedChargeController
from runtime.charge.runtime.desulfation_completion import (
    DesulfationCompletionInput,
    apply_desulfation_completion_effect,
    build_desulfation_completion_effect,
    complete_desulfation_to_safe_wait,
)
from runtime.charge.decisions import AuthorityAction
from runtime.charge.strategy.desulfation import DesulfationAction, decide_desulfation
from runtime.charge.strategy.recovery_safe_wait import RecoverySafeWaitContinuation
from runtime.charge.runtime.variables import DELTA_MONITOR_DELAY_S

ROOT = Path(__file__).resolve().parents[1]


_UNSET = object()


def _input(host, *, session_id=_UNSET, generation=_UNSET):
    return DesulfationCompletionInput(
        session_id=host._v2_trace_session_id if session_id is _UNSET else session_id,
        session_generation=host._v2_trace_started_at if generation is _UNSET else generation,
        source_stage=host.STAGE_DESULFATION, safe_wait_stage=host.STAGE_SAFE_WAIT,
        next_stage=host.STAGE_MAIN, main_target_voltage_v=14.4,
        main_target_current_a=3.2, recovery_attempt=2, agm_stage_idx=1,
        now_s=9000.0, ah=8.5, voltage_v=15.4, measured_current_a=1.1,
        temperature_c=25.0,
        log_event_end={"stage": host.STAGE_DESULFATION, "trigger": "bounded intermediate recovery 2h complete"},
    )


class DesulfationCompletionEffectTests(unittest.TestCase):
    def _host(self, profile):
        host = ManagedChargeController(object())
        host.battery_type = profile
        host.ah_capacity = 90
        host._v2_trace_session_id = "session-a"
        host._v2_trace_started_at = 1000.0
        host._stage_tracking_enabled = True
        host.current_stage = host.STAGE_DESULFATION
        host.stage_start_time = 1800.0
        host._stage_start_ah = 2.0
        host._restored_target_v, host._restored_target_i = 13.8, 2.0
        host._main_sample_evidence.plateau_since_s = 33.0
        return host

    def test_profile_targets_and_completion_effect_lifecycle_parity(self):
        for profile in ("Ca/Ca", "EFB", "AGM"):
            with self.subTest(profile=profile):
                host = self._host(profile)
                target_v, target_i = host._main_target(25.0)
                value = _input(host)
                value = DesulfationCompletionInput(**{
                    **value.__dict__, "main_target_voltage_v": target_v,
                    "main_target_current_a": target_i,
                })
                effect = build_desulfation_completion_effect(value)
                actions = {}
                self.assertTrue(apply_desulfation_completion_effect(host, effect, actions))
                self.assertEqual(set(actions), {"log_event_end", "turn_off", "notify", "log_event"})
                self.assertIs(actions["turn_off"], True)
                self.assertNotIn("turn_on", actions)
                self.assertEqual(actions["log_event_end"], dict(value.log_event_end))
                self.assertIn("Ожидание падения", actions["notify"])
                self.assertEqual(actions["log_event"], "START | INTERMEDIATE_RECOVERY_COMPLETE")
                self.assertEqual(host.current_stage, host.STAGE_SAFE_WAIT)
                self.assertEqual(len(host._stage_history), 2)
                self.assertEqual((host.stage_start_time, host._stage_start_ah), (9000.0, 8.5))
                self.assertEqual((host._safe_wait_next_stage, host._safe_wait_target_v,
                                  host._safe_wait_target_i, host._safe_wait_start),
                                 (host.STAGE_MAIN, target_v, target_i, 9000.0))
                continuation = host._recovery_safe_wait
                self.assertIsInstance(continuation, RecoverySafeWaitContinuation)
                self.assertEqual((continuation.source_stage, continuation.next_stage,
                                  continuation.session_id, continuation.session_generation,
                                  continuation.recovery_attempt, continuation.agm_stage_idx),
                                 (host.STAGE_DESULFATION, host.STAGE_MAIN, "session-a", 1000.0, 2, 1))
                self.assertIsNone(host._main_sample_evidence.plateau_since_s)
                self.assertGreaterEqual(host._last_safe_wait_sample, 9000.0)

    def test_invalid_identity_fails_closed_without_mutation_or_action(self):
        for session_id, generation in ((None, 1000.0), ("other", 1000.0),
                                       ("session-a", 1001.0), ("session-a", None)):
            host = self._host("EFB")
            effect = build_desulfation_completion_effect(_input(host, session_id=session_id, generation=generation))
            actions = {}
            self.assertFalse(apply_desulfation_completion_effect(host, effect, actions))
            self.assertEqual(host.current_stage, host.STAGE_DESULFATION)
            self.assertIsNone(host._recovery_safe_wait)
            self.assertEqual(actions, {})

    def test_duration_authority_and_single_existing_caller(self):
        self.assertEqual(decide_desulfation(active_elapsed_s=7199.99).action, DesulfationAction.CONTINUE)
        self.assertEqual(decide_desulfation(active_elapsed_s=7200.0).action, DesulfationAction.COMPLETE_TO_SAFE_WAIT)
        tree = ast.parse((ROOT / "charge_controller.py").read_text(encoding="utf-8"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ManagedChargeController")
        names = {n.name for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.assertNotIn("_complete_desulfation_to_safe_wait", names)
        dispatch = ast.parse((ROOT / "runtime/charge/runtime/stage_authority.py").read_text(encoding="utf-8"))
        controller_calls = [n for n in ast.walk(dispatch) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                            and n.func.id == "apply_desulfation_authority_tick"]
        self.assertEqual(len(controller_calls), 1)
        self.assertFalse(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                            and n.func.id in {"apply_desulfation_completion_effect",
                                              "build_desulfation_completion_effect",
                                              "DesulfationCompletionInput"} for n in ast.walk(tree)))
        owner = ast.parse((ROOT / "runtime/charge/runtime/desulfation_completion.py").read_text(encoding="utf-8"))
        calls = [n for n in ast.walk(owner) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == "apply_desulfation_completion_effect"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                             and n.func.id == "build_desulfation_completion_effect" for n in ast.walk(owner)), 1)
        recovery = ast.parse((ROOT / "runtime/charge/runtime/recovery_scaffold.py").read_text(encoding="utf-8"))
        recovery_source = (ROOT / "runtime/charge/runtime/recovery_scaffold.py").read_text(encoding="utf-8")
        self.assertEqual(sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                             and n.func.id == "complete_desulfation_to_safe_wait"
                             for n in ast.walk(recovery)), 1)
        self.assertEqual(sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                             and n.func.id == "decide_desulfation"
                             for n in ast.walk(recovery)), 1)
        authority_owner = recovery_source[
            recovery_source.index("def apply_desulfation_authority_tick("):
            recovery_source.index("def _output_is_known(")
        ]
        for forbidden in ("execution_port", ".turn_on(", ".turn_off(", ".set_voltage(", ".set_output("):
            self.assertNotIn(forbidden, authority_owner)
        for node in ast.walk(owner):
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn("charge_controller", node.module or "")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr.lower(), {"set_voltage", "set_current", "set_output", "turn_on"})
        self.assertGreater(float(DELTA_MONITOR_DELAY_S.default), 0.0)

    def test_controller_dispatch_parity_and_event_capture_failure_is_read_only(self):
        host = self._host("EFB")
        actions = {}
        decision = host._apply_stage_authority(
            record=None, first_stage=None, stage_before=host.STAGE_DESULFATION,
            timestamp_s=9000.0, voltage=15.4, current=1.1, temp=25.0, ah=8.5,
            is_cv=False, is_cc=False, actions=actions,
        )
        target_v, target_i = host._main_target(25.0)
        self.assertEqual(decision.action, AuthorityAction.COMPLETE_TO_SAFE_WAIT)
        self.assertEqual(host._safe_wait_target_v, target_v)
        self.assertEqual(host._safe_wait_target_i, target_i)
        self.assertEqual(actions["log_event_end"], {
            "stage": host.STAGE_DESULFATION, "time_sec": 7200.0,
            "ah_on_stage": 6.5, "ah": 8.5, "t": 25.0, "v": 15.4,
            "i": 1.1, "trigger": "bounded intermediate recovery 2h complete",
        })

        failed = self._host("EFB")
        before = (failed.current_stage, failed.stage_start_time, failed._stage_start_ah,
                  failed._recovery_safe_wait, tuple(failed._stage_history))
        failed._make_log_event_end = lambda *args: (_ for _ in ()).throw(RuntimeError("capture failed"))
        failed_actions = {}
        self.assertFalse(complete_desulfation_to_safe_wait(
            failed, main_target_voltage_v=14.4, main_target_current_a=3.2,
            now_s=9000.0, ah=8.5, voltage_v=15.4, measured_current_a=1.1,
            temperature_c=25.0, actions=failed_actions,
        ))
        self.assertEqual((failed.current_stage, failed.stage_start_time, failed._stage_start_ah,
                          failed._recovery_safe_wait, tuple(failed._stage_history)), before)
        self.assertEqual(failed_actions, {})


if __name__ == "__main__":
    unittest.main()
