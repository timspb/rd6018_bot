import ast
import inspect
import unittest
from pathlib import Path

from charge_controller import ManagedChargeController
from runtime.charge.runtime import agm_step_advance as owner
from runtime.safety.variables import PROTECTION_OCP_MARGIN_A, PROTECTION_OVP_MARGIN_V


ROOT = Path(__file__).resolve().parents[1]


class AgmStepAdvanceEffectTests(unittest.TestCase):
    def _controller(self):
        controller = ManagedChargeController(object())
        controller.start(ManagedChargeController.PROFILE_AGM, 90)
        controller.current_stage = controller.STAGE_MAIN
        controller._agm_stage_idx = 0
        controller.stage_start_time = 100.0
        controller._stage_start_ah = 1.0
        return controller

    def test_effect_is_frozen_and_clamps_next_stage_index(self):
        effect = owner.build_agm_step_advance_effect(
            current_stage_index=0,
            stage_count=4,
            now_s=1000.0,
            ah=3.0,
            temperature_c=25.0,
            reason="agm_tail_hold_complete_advance_step",
        )
        self.assertEqual(effect.next_stage_index, 1)
        with self.assertRaises((AttributeError, TypeError)):
            effect.next_stage_index = 2

        last = owner.build_agm_step_advance_effect(
            current_stage_index=3,
            stage_count=4,
            now_s=1000.0,
            ah=3.0,
            temperature_c=25.0,
            reason="x",
        )
        self.assertEqual(last.next_stage_index, 3)

    def test_applicator_preserves_target_limits_and_resets(self):
        controller = self._controller()
        actions = {}
        controller._delta_monitor_start = 500.0
        controller._transition_blanking_until = 500.0
        controller._main_sample_evidence.plateau_since_s = 400.0

        effect = owner.build_agm_step_advance_effect(
            current_stage_index=controller._agm_stage_idx,
            stage_count=4,
            now_s=1000.0,
            ah=3.0,
            temperature_c=25.0,
            reason="agm_tail_hold_complete_advance_step",
        )
        owner.apply_agm_step_advance_effect(controller, effect, actions)

        self.assertEqual(controller._agm_stage_idx, 1)
        self.assertEqual(controller.stage_start_time, 1000.0)
        self.assertEqual(controller._stage_start_ah, 3.0)
        expected_v, expected_i = controller._main_target(25.0)
        self.assertEqual(actions["set_voltage"], expected_v)
        self.assertEqual(actions["set_current"], expected_i)
        self.assertAlmostEqual(
            actions["set_ovp"], expected_v + float(PROTECTION_OVP_MARGIN_V.default)
        )
        self.assertAlmostEqual(
            actions["set_ocp"], expected_i + float(PROTECTION_OCP_MARGIN_A.default)
        )
        self.assertEqual(controller._phase_current_limit, expected_i)
        self.assertEqual(actions["log_event"], "V2_AGM_STEP_2")
        self.assertIn("2/4", actions["notify"])
        self.assertIsNone(controller._main_sample_evidence.plateau_since_s)

    def test_cold_target_uses_existing_temperature_compensation_after_index_update(self):
        controller = self._controller()
        actions = {}
        effect = owner.build_agm_step_advance_effect(
            current_stage_index=0,
            stage_count=4,
            now_s=1000.0,
            ah=3.0,
            temperature_c=0.0,
            reason="cold",
        )
        owner.apply_agm_step_advance_effect(controller, effect, actions)
        expected_v, expected_i = controller._main_target(0.0)
        self.assertEqual(actions["set_voltage"], expected_v)
        self.assertEqual(actions["set_current"], expected_i)

    def test_old_controller_mutator_absent_and_single_owner_application(self):
        source = (ROOT / "charge_controller.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        methods = [
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertNotIn("_advance_agm_step", methods)
        self.assertNotIn("self._advance_agm_step", source)
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "apply_authoritative_stage_tick"
        ]
        self.assertEqual(len(calls), 1)
        dispatch = ast.parse((ROOT / "runtime/charge/runtime/stage_authority.py").read_text(encoding="utf-8"))
        self.assertEqual(sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                             and n.func.id == "apply_main_authority_tick" for n in ast.walk(dispatch)), 1)
        owner_tree = ast.parse((ROOT / "runtime/charge/runtime/main_scaffold.py").read_text(encoding="utf-8"))
        effect_calls = [
            node for node in ast.walk(owner_tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "apply_agm_step_advance_effect"
        ]
        self.assertEqual(len(effect_calls), 1)

        owner_source = inspect.getsource(owner)
        for forbidden in ("execution_port", "turn_on", "turn_off", "set_output"):
            self.assertNotIn(forbidden, owner_source)


if __name__ == "__main__":
    unittest.main()
