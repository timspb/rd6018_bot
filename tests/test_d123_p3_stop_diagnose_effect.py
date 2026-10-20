import ast
import inspect
import unittest
from pathlib import Path
from types import MappingProxyType
from unittest.mock import Mock

from charge_controller import ManagedChargeController
from runtime.charge.runtime import stop_diagnose as owner
from runtime.charge.persistence import (
    DONE_COMPLETION_TERMINAL,
    DONE_OUTPUT_OFF,
    TerminalPersistenceRequest,
)


ROOT = Path(__file__).resolve().parents[1]


class StopDiagnoseEffectTests(unittest.TestCase):
    def _controller(self):
        controller = ManagedChargeController(object())
        controller.start(ManagedChargeController.PROFILE_EFB, 70)
        controller.current_stage = controller.STAGE_MAIN
        controller._recovery_safe_wait = object()
        controller._final_safe_wait = object()
        controller.finish_timer_start = 123.0
        return controller

    def test_effect_is_frozen_and_preserves_exact_actions(self):
        value = owner.StopDiagnoseInput(
            source_stage="Main Charge",
            done_stage="Done",
            now_s=1000.0,
            voltage_v=14.8,
            current_a=1.2,
            temperature_c=25.0,
            ah=4.0,
            reason="synthetic_reason",
            log_event_end={"stage": "Main Charge", "reason": "synthetic_reason"},
        )
        effect = owner.build_stop_diagnose_effect(value)
        self.assertIsInstance(effect.action_values, MappingProxyType)
        self.assertIsInstance(effect.log_event_end, MappingProxyType)
        self.assertTrue(effect.action_values["turn_off"])
        self.assertEqual(effect.action_values["log_event"], "V2_STOP_DIAGNOSE")
        self.assertIn("synthetic_reason", effect.action_values["notify"])
        with self.assertRaises(TypeError):
            effect.action_values["turn_off"] = False

    def test_application_commits_done_state_resets_and_save_order(self):
        controller = self._controller()
        actions = {}
        save = Mock()
        controller._save_session = save
        before_history = len(controller._stage_history)

        owner.apply_stop_and_diagnose(
            controller,
            actions=actions,
            now=1000.0,
            voltage=14.8,
            current=1.2,
            temp=25.0,
            ah=4.0,
            reason="synthetic_reason",
        )

        self.assertEqual(controller.current_stage, controller.STAGE_DONE)
        self.assertEqual(len(controller._stage_history), before_history + 1)
        self.assertEqual(controller._stage_history[-1]["from"], controller.STAGE_MAIN)
        self.assertEqual(controller._stage_history[-1]["to"], controller.STAGE_DONE)
        self.assertIsNone(controller._recovery_safe_wait)
        self.assertIsNone(controller._final_safe_wait)
        self.assertIsNone(controller.finish_timer_start)
        self.assertEqual(controller.stage_start_time, 1000.0)
        self.assertEqual(controller._stage_start_ah, 4.0)
        self.assertTrue(actions["turn_off"])
        self.assertEqual(actions["log_event"], "V2_STOP_DIAGNOSE")
        save.assert_called_once_with(
            14.8, 1.2, 4.0,
            terminal_request=TerminalPersistenceRequest(
                DONE_COMPLETION_TERMINAL, DONE_OUTPUT_OFF, 14.8, 1.2, 4.0
            ),
        )

    def test_save_failure_keeps_existing_pre_save_mutation_semantics(self):
        controller = self._controller()
        controller._save_session = Mock(side_effect=RuntimeError("disk full"))
        actions = {}
        with self.assertRaisesRegex(RuntimeError, "disk full"):
            owner.apply_stop_and_diagnose(
                controller,
                actions=actions,
                now=1000.0,
                voltage=14.8,
                current=1.2,
                temp=25.0,
                ah=4.0,
                reason="synthetic_reason",
            )
        self.assertEqual(controller.current_stage, controller.STAGE_DONE)
        self.assertTrue(actions["turn_off"])
        self.assertEqual(actions["log_event"], "V2_STOP_DIAGNOSE")

    def test_controller_has_no_old_mutator_and_all_calls_use_owner(self):
        controller_source = (ROOT / "charge_controller.py").read_text(encoding="utf-8")
        tree = ast.parse(controller_source)
        methods = [
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertNotIn("_stop_and_diagnose", methods)
        self.assertNotIn("self._stop_and_diagnose", controller_source)
        app_source = (ROOT / "application" / "charge_session_tick.py").read_text(encoding="utf-8")
        app_tree = ast.parse(app_source)
        calls = [
            node for node in ast.walk(app_tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "apply_stop_and_diagnose"
        ]
        self.assertGreaterEqual(len(calls), 1)

        owner_source = inspect.getsource(owner)
        for forbidden in ("execution_port", "set_voltage", "set_current", "set_ovp", "set_ocp", "turn_on"):
            self.assertNotIn(forbidden, owner_source)


if __name__ == "__main__":
    unittest.main()
