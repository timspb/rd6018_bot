"""Sprint 32 MAIN decision/effect dispatch ownership and parity guards."""

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from charge_controller import ManagedChargeController
from runtime.charge.decisions import AuthorityAction, AuthorityDecision
from runtime.charge.runtime.main_scaffold import apply_main_authority_tick


ROOT = Path(__file__).resolve().parents[1]


def _record():
    return SimpleNamespace(
        decision=SimpleNamespace(decision="fixture-policy"),
        analysis=SimpleNamespace(
            metrics=SimpleNamespace(seconds_since_current_min=321.0)
        ),
    )


class MainAuthorityDispatchTests(unittest.TestCase):
    def _host(self, profile="Ca/Ca"):
        host = ManagedChargeController(object())
        host.start(profile, 90)
        host.current_stage = host.STAGE_MAIN
        host.stage_start_time = 900.0
        host._stage_start_ah = 2.0
        return host

    def test_decision_input_assembly_keeps_current_authority_values(self):
        host = self._host("AGM")
        expected = AuthorityDecision(AuthorityAction.CONTINUE, "fixture")
        with patch(
            "runtime.charge.strategy.main_authority.decide_main_transition",
            return_value=expected,
        ) as decide:
            result = apply_main_authority_tick(
                host, record=_record(), first_stage=None, timestamp_s=800.0,
                voltage=14.6, current=0.19, temp=24.0, ah=3.0,
                is_cv=True, actions={},
            )
        self.assertIs(result, expected)
        values = decide.call_args.kwargs
        self.assertEqual(values["profile"], "AGM")
        self.assertEqual(values["intent"], host._v2_intent)
        self.assertEqual(values["policy_decision"], "fixture-policy")
        self.assertEqual(values["seconds_since_current_min"], 321.0)
        self.assertEqual(values["agm_stage_idx"], 0)
        self.assertEqual(values["desulf_attempts"], host.antisulfate_count)
        self.assertEqual(values["main_elapsed_s"], 0.0)
        self.assertEqual(values["current_a"], 0.19)
        self.assertTrue(values["is_cv"])

    def test_each_main_outcome_uses_the_existing_single_effect_path(self):
        cases = (
            ("AGM", AuthorityAction.ADVANCE_AGM_STEP, "Main Charge", None),
            ("Ca/Ca", AuthorityAction.ENTER_DESULFATION, "Десульфатация", "set_ovp"),
            ("EFB", AuthorityAction.ENTER_MIX, "Mix Mode", "set_ocp"),
            ("Ca/Ca", AuthorityAction.COMPLETE_TO_SAFE_WAIT, "Безопасное ожидание", "turn_off"),
            ("Ca/Ca", AuthorityAction.STOP_AND_DIAGNOSE, "Done", "turn_off"),
        )
        for profile, action, expected_stage, expected_action in cases:
            with self.subTest(action=action):
                host = self._host(profile)
                actions = {}
                decision = AuthorityDecision(action, "fixture-reason")
                with patch(
                    "runtime.charge.strategy.main_authority.decide_main_transition",
                    return_value=decision,
                ):
                    result = apply_main_authority_tick(
                        host, record=_record(), first_stage=None,
                        timestamp_s=1000.0, voltage=14.5, current=0.2,
                        temp=24.0, ah=3.0, is_cv=True, actions=actions,
                    )
                self.assertIs(result, decision)
                self.assertEqual(host.current_stage, expected_stage)
                if expected_action is not None:
                    self.assertIn(expected_action, actions)
                if action == AuthorityAction.ADVANCE_AGM_STEP:
                    self.assertEqual(host._agm_stage_idx, 1)
                    self.assertIn("set_voltage", actions)
                    self.assertIn("set_current", actions)

    def test_controller_has_one_dispatch_and_no_inline_main_policy_or_effects(self):
        controller = ast.parse((ROOT / "charge_controller.py").read_text(encoding="utf-8"))
        calls = [
            node for node in ast.walk(controller)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "apply_main_authority_tick"
        ]
        self.assertEqual(len(calls), 1)
        forbidden = {
            "decide_main_transition", "apply_agm_step_advance_effect",
            "apply_main_desulfation_entry", "apply_main_mix_entry",
            "apply_main_completion_to_safe_wait",
        }
        self.assertFalse(any(
            isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in forbidden
            for node in ast.walk(controller)
        ))

        owner_path = ROOT / "runtime/charge/runtime/main_scaffold.py"
        owner_source = owner_path.read_text(encoding="utf-8")
        function = owner_source[
            owner_source.index("def apply_main_authority_tick("):
            owner_source.index("def _output_is_known(")
        ]
        for text in ("execution_port", ".turn_on(", ".turn_off(", ".set_voltage(", ".set_output("):
            self.assertNotIn(text, function)
        self.assertNotIn("charge_controller", function)


if __name__ == "__main__":
    unittest.main()
