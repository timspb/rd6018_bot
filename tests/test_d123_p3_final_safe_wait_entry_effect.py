import ast
import inspect
import unittest
from pathlib import Path

from charge_controller import ManagedChargeController
from runtime.charge.runtime import final_safe_wait_entry as owner


ROOT = Path(__file__).resolve().parents[1]


class DummyHass:
    pass


class FinalSafeWaitEntryEffectTests(unittest.TestCase):
    def _controller(self, profile, stage):
        controller = ManagedChargeController(DummyHass())
        controller.start(profile, 90)
        controller._v2_trace_session_id = "entry-session"
        controller.current_stage = stage
        return controller

    def _input(self, controller, *, session_id="entry-session", generation=None):
        target_v, target_i = controller._storage_target()
        return owner.FinalSafeWaitEntryInput(
            source_stage=controller.current_stage,
            safe_wait_stage=controller.STAGE_SAFE_WAIT,
            next_stage=controller.STAGE_DONE,
            session_id=session_id,
            session_generation=(controller._v2_trace_started_at if generation is None else generation),
            target_voltage_v=target_v,
            target_current_a=target_i,
            now_s=1000.0,
            voltage_v=16.2,
            current_a=0.5,
            temperature_c=25.0,
            ah=10.0,
            reason="confirmed_delta_finish_hold_complete",
            log_event_end={"stage": controller.current_stage, "trigger": "confirmed_delta_finish_hold_complete"},
        )

    def test_ca_efb_agm_keep_targets_actions_and_single_stage_history_edge(self):
        for profile in (
            ManagedChargeController.PROFILE_CA,
            ManagedChargeController.PROFILE_EFB,
            ManagedChargeController.PROFILE_AGM,
        ):
            with self.subTest(profile=profile):
                controller = self._controller(profile, ManagedChargeController.STAGE_MIX)
                expected = controller._storage_target()
                history_before = len(controller._stage_history)
                actions = {}
                self.assertTrue(owner.apply_final_safe_wait_entry(controller, self._input(controller), actions))
                self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)
                self.assertEqual(controller._safe_wait_next_stage, controller.STAGE_DONE)
                self.assertEqual(
                    (controller._safe_wait_target_v, controller._safe_wait_target_i), expected
                )
                self.assertEqual(len(controller._stage_history), history_before + 1)
                self.assertEqual(
                    (controller._stage_history[-1]["from"], controller._stage_history[-1]["to"]),
                    (controller.STAGE_MIX, controller.STAGE_SAFE_WAIT),
                )
                self.assertTrue(actions["turn_off"])
                self.assertEqual(actions["log_event"], "START | V2_AUTHORITATIVE")
                self.assertEqual(actions["log_event_end"]["stage"], controller.STAGE_MIX)
                self.assertIn("confirmed_delta_finish_hold_complete", actions["notify"])
                self.assertIsNone(controller.finish_timer_start)

    def test_missing_or_stale_identity_fails_before_any_mutation_or_on_intent(self):
        for kwargs in ({"session_id": None}, {"generation": 1.0}):
            controller = self._controller(ManagedChargeController.PROFILE_AGM, ManagedChargeController.STAGE_MIX)
            before = (controller.current_stage, list(controller._stage_history), controller.stage_start_time)
            actions = {}
            self.assertFalse(owner.apply_final_safe_wait_entry(controller, self._input(controller, **kwargs), actions))
            self.assertEqual((controller.current_stage, list(controller._stage_history), controller.stage_start_time), before)
            self.assertEqual(actions, {})
            self.assertNotIn("turn_on", actions)

    def test_effect_is_immutable_and_old_controller_mutator_is_absent(self):
        controller = self._controller(ManagedChargeController.PROFILE_AGM, ManagedChargeController.STAGE_MIX)
        effect = owner.build_final_safe_wait_entry_effect(self._input(controller))
        with self.assertRaises(TypeError):
            effect.action_values["turn_off"] = False
        self.assertFalse(hasattr(controller, "_enter_safe_wait_done"))

    def test_ast_keeps_one_effect_applicator_and_no_physical_writer(self):
        source = inspect.getsource(owner)
        tree = ast.parse(source)
        effect_calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "apply_final_safe_wait_entry_effect"
        ]
        self.assertEqual(len(effect_calls), 1)
        for forbidden in ("set_voltage", "set_current", "set_ovp", "set_ocp", "set_output"):
            self.assertNotIn(f'"{forbidden}"', source)
        controller_tree = ast.parse((ROOT / "charge_controller.py").read_text(encoding="utf-8"))
        methods = [node.name for node in ast.walk(controller_tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        self.assertNotIn("_enter_safe_wait_done", methods)


if __name__ == "__main__":
    unittest.main()
