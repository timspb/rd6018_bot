import ast
import inspect
import unittest
from pathlib import Path
from types import MappingProxyType

from charge_controller import ManagedChargeController
from runtime.charge.runtime import prep_completion as owner


ROOT = Path(__file__).resolve().parents[1]


class PrepCompletionEffectTests(unittest.TestCase):
    def test_builder_returns_frozen_exact_transition_payload(self):
        value = owner.PrepCompletionInput(
            source_stage="PREP",
            prep_stage="PREP",
            main_stage="MAIN",
            now_s=1000.0,
            ah=2.0,
            battery_capacity_ah=70.0,
            profile="EFB",
            target_voltage_v=14.4,
            target_current_a=2.0,
            actions={"log_event_end": {"stage": "PREP"}, "set_ovp": 14.5, "set_ocp": 2.1},
        )
        effect = owner.build_prep_completion_effect(value)
        self.assertIsInstance(effect.action_values, MappingProxyType)
        self.assertIsInstance(effect.action_values["log_event_end"], MappingProxyType)
        self.assertEqual(effect.action_values["set_voltage"], 14.4)
        self.assertEqual(effect.action_values["set_current"], 2.0)
        self.assertEqual(effect.action_values["set_ovp"], 14.5)
        self.assertEqual(effect.action_values["set_ocp"], 2.1)
        with self.assertRaises(TypeError):
            effect.action_values["turn_on"] = True
        with self.assertRaises(TypeError):
            effect.action_values["log_event_end"]["stage"] = "MIX"

    def test_applicator_commits_one_stage_edge_and_preserves_action_values(self):
        controller = ManagedChargeController(object())
        controller.start(ManagedChargeController.PROFILE_EFB, 70)
        controller.current_stage = controller.STAGE_PREP
        before = len(controller._stage_history)
        effect = owner.build_prep_completion_effect(owner.PrepCompletionInput(
            source_stage=controller.STAGE_PREP,
            prep_stage=controller.STAGE_PREP,
            main_stage=controller.STAGE_MAIN,
            now_s=1000.0,
            ah=2.0,
            battery_capacity_ah=70.0,
            profile="EFB",
            target_voltage_v=14.4,
            target_current_a=2.0,
            actions={"log_event_end": {"stage": "PREP"}, "set_ovp": 14.5, "set_ocp": 2.1},
        ))
        actions = {"existing": "retained"}
        self.assertTrue(owner.apply_prep_completion_effect(controller, effect, actions))
        self.assertEqual(controller.current_stage, controller.STAGE_MAIN)
        self.assertEqual(len(controller._stage_history), before + 1)
        self.assertEqual(controller._stage_history[-1]["from"], controller.STAGE_PREP)
        self.assertEqual(controller._stage_history[-1]["to"], controller.STAGE_MAIN)
        self.assertEqual(controller.stage_start_time, 1000.0)
        self.assertEqual(controller._stage_start_ah, 2.0)
        self.assertEqual(controller._start_ah, 2.0)
        self.assertEqual(actions["existing"], "retained")
        self.assertNotIn("turn_on", actions)

    def test_source_has_one_residual_entry_application_and_no_setters(self):
        scaffold = (ROOT / "runtime/charge/runtime/residual_scaffold.py").read_text(encoding="utf-8")
        tree = ast.parse(scaffold)
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "apply_prep_completion_effect"
        ]
        self.assertEqual(len(calls), 1)

        source = inspect.getsource(owner)
        owner_tree = ast.parse(source)
        method_calls = [
            node.func.attr for node in ast.walk(owner_tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        ]
        for forbidden in ("set_voltage", "set_current", "set_ovp", "set_ocp", "turn_on", "turn_off"):
            self.assertNotIn(forbidden, method_calls)
        self.assertNotIn('"turn_on"', source)


if __name__ == "__main__":
    unittest.main()
