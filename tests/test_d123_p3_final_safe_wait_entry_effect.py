import ast
import inspect
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from charge_controller import ManagedChargeController
from runtime.charge.decisions import AuthorityAction, AuthorityDecision
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

    def test_mix_completion_owner_dispatches_existing_entry_and_rejects_stale_identity(self):
        controller = self._controller(
            ManagedChargeController.PROFILE_EFB, ManagedChargeController.STAGE_MIX
        )
        controller.finish_timer_start = 700.0
        controller._delta_trigger_mode = "CV"
        target_v, target_i = controller._storage_target()
        actions = {}
        self.assertTrue(owner.apply_mix_completion_to_safe_wait(
            controller,
            now_s=1000.0,
            voltage_v=16.2,
            current_a=0.5,
            temperature_c=25.0,
            ah=10.0,
            reason="confirmed_delta_finish_hold_complete",
            target_voltage_v=target_v,
            target_current_a=target_i,
            actions=actions,
        ))
        self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)
        self.assertEqual(actions["log_event_end"]["stage"], controller.STAGE_MIX)
        self.assertEqual(actions["log_event"], "START | V2_AUTHORITATIVE")
        self.assertTrue(actions["turn_off"])
        self.assertNotIn("turn_on", actions)

        stale = self._controller(
            ManagedChargeController.PROFILE_EFB, ManagedChargeController.STAGE_MIX
        )
        stale._v2_trace_session_id = None
        before = (stale.current_stage, list(stale._stage_history), stale.stage_start_time)
        rejected = {}
        self.assertFalse(owner.apply_mix_completion_to_safe_wait(
            stale,
            now_s=1000.0,
            voltage_v=16.2,
            current_a=0.5,
            temperature_c=25.0,
            ah=10.0,
            reason="confirmed_delta_finish_hold_complete",
            target_voltage_v=target_v,
            target_current_a=target_i,
            actions=rejected,
        ))
        self.assertEqual(
            (stale.current_stage, list(stale._stage_history), stale.stage_start_time), before
        )
        self.assertEqual(rejected, {})

    def test_main_completion_owner_preserves_parity_and_rejects_stale_identity(self):
        for profile in (
            ManagedChargeController.PROFILE_CA,
            ManagedChargeController.PROFILE_EFB,
            ManagedChargeController.PROFILE_AGM,
        ):
            with self.subTest(profile=profile):
                controller = self._controller(profile, ManagedChargeController.STAGE_MAIN)
                target_v, target_i = controller._storage_target()
                actions = {}
                self.assertTrue(owner.apply_main_completion_to_safe_wait(
                    controller,
                    now_s=1000.0,
                    voltage_v=15.1,
                    current_a=0.4,
                    temperature_c=24.0,
                    ah=12.0,
                    reason="main_completion",
                    target_voltage_v=target_v,
                    target_current_a=target_i,
                    actions=actions,
                ))
                self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)
                self.assertEqual(controller._safe_wait_next_stage, controller.STAGE_DONE)
                self.assertEqual(
                    (controller._safe_wait_target_v, controller._safe_wait_target_i),
                    (target_v, target_i),
                )
                self.assertEqual(actions["log_event_end"]["stage"], controller.STAGE_MAIN)
                self.assertEqual(actions["log_event"], "START | V2_AUTHORITATIVE")
                self.assertTrue(actions["turn_off"])
                self.assertNotIn("turn_on", actions)

        stale = self._controller(
            ManagedChargeController.PROFILE_EFB, ManagedChargeController.STAGE_MAIN
        )
        stale._v2_trace_session_id = None
        before = (stale.current_stage, list(stale._stage_history), stale.stage_start_time)
        rejected = {}
        target_v, target_i = stale._storage_target()
        self.assertFalse(owner.apply_main_completion_to_safe_wait(
            stale,
            now_s=1000.0,
            voltage_v=15.1,
            current_a=0.4,
            temperature_c=24.0,
            ah=12.0,
            reason="main_completion",
            target_voltage_v=target_v,
            target_current_a=target_i,
            actions=rejected,
        ))
        self.assertEqual(
            (stale.current_stage, list(stale._stage_history), stale.stage_start_time), before
        )
        self.assertEqual(rejected, {})

        record = SimpleNamespace(
            decision=SimpleNamespace(decision=None),
            analysis=SimpleNamespace(metrics=SimpleNamespace(seconds_since_current_min=0.0)),
        )
        stale_actions = {}
        with patch(
            "charge_controller.decide_main_transition",
            return_value=AuthorityDecision(AuthorityAction.COMPLETE_TO_SAFE_WAIT, "main_completion"),
        ):
            result = stale._apply_authoritative_decision(
                record=record,
                first_stage=None,
                stage_before=stale.STAGE_MAIN,
                timestamp_s=1000.0,
                voltage=15.1,
                current=0.4,
                temp=24.0,
                ah=12.0,
                is_cv=True,
                is_cc=False,
                actions=stale_actions,
            )
        self.assertEqual(result.action, AuthorityAction.STOP_AND_DIAGNOSE)
        self.assertEqual(stale.current_stage, stale.STAGE_DONE)
        self.assertTrue(stale_actions["turn_off"])
        self.assertNotIn("turn_on", stale_actions)

    def test_main_completion_cut_has_one_controller_dispatch_and_owner_assembly(self):
        source = (ROOT / "charge_controller.py").read_text(encoding="utf-8")
        controller_tree = ast.parse(source)
        method = next(
            node for node in ast.walk(controller_tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "_apply_authoritative_decision"
        )
        main_dispatches = [
            node for node in ast.walk(method)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "apply_main_completion_to_safe_wait"
        ]
        inline_inputs = [
            node for node in ast.walk(method)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "FinalSafeWaitEntryInput"
        ]
        self.assertEqual(len(main_dispatches), 1)
        self.assertEqual(inline_inputs, [])
        main_branch = source[
            source.index("if stage_before == self.STAGE_MAIN:", source.index("def _apply_authoritative_decision")):
            source.index("return apply_mix_authority_tick(", source.index("def _apply_authoritative_decision"))
        ]
        complete_branch = main_branch[
            main_branch.index("elif decision.action == AuthorityAction.COMPLETE_TO_SAFE_WAIT:"):
            main_branch.index("elif decision.action == AuthorityAction.STOP_AND_DIAGNOSE:")
        ]
        self.assertEqual(complete_branch.count("apply_main_completion_to_safe_wait("), 1)
        self.assertNotIn("FinalSafeWaitEntryInput(", complete_branch)
        self.assertIn("self._storage_target()", complete_branch)
        self.assertIn("apply_stop_and_diagnose(", complete_branch)
        owner_source = inspect.getsource(owner)
        self.assertIn("def apply_main_completion_to_safe_wait(", owner_source)
        for forbidden in ("execution_port", '"set_voltage"', '"set_current"', '"set_ovp"', '"set_ocp"', '"set_output"'):
            self.assertNotIn(forbidden, owner_source)

    def test_mix_completion_cut_is_single_dispatch_without_physical_writer(self):
        source = (ROOT / "runtime/charge/runtime/mix_scaffold.py").read_text(encoding="utf-8")
        mix_branch = source[source.index("elif decision.action == AuthorityAction.COMPLETE_TO_SAFE_WAIT:"):source.index("elif decision.action == AuthorityAction.STOP_AND_DIAGNOSE:")]
        self.assertIn("apply_mix_completion_to_safe_wait(", mix_branch)
        self.assertNotIn("FinalSafeWaitEntryInput(", mix_branch)
        owner_source = inspect.getsource(owner)
        for forbidden in ("execution_port", '"set_voltage"', '"set_current"', '"set_ovp"', '"set_ocp"', '"set_output"'):
            self.assertNotIn(forbidden, owner_source)

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
