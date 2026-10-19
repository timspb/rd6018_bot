import ast
import inspect
import unittest
from pathlib import Path
from types import MappingProxyType

from charge_controller import ManagedChargeController
from runtime.charge.runtime import final_safe_wait_completion as owner
from tests.d123_final_safe_wait_helpers import enter_final_safe_wait


ROOT = Path(__file__).resolve().parents[1]


class DummyHass:
    pass


class FinalSafeWaitCompletionEffectTests(unittest.TestCase):
    def _controller(self):
        controller = ManagedChargeController(DummyHass())
        controller.start(ManagedChargeController.PROFILE_AGM, 90)
        controller._v2_trace_session_id = "completion-session"
        controller.current_stage = controller.STAGE_MIX
        enter_final_safe_wait(
            controller,
            actions={},
            now=1000.0,
            voltage=16.2,
            current=0.5,
            temp=25.0,
            ah=10.0,
            reason="confirmed_delta_finish_hold_complete",
        )
        transition = {
            "kind": "final_safe_wait_to_done",
            "session_id": controller._final_safe_wait.session_id,
            "session_generation": controller._final_safe_wait.session_generation,
            "started_at": controller._final_safe_wait.started_at,
            "reason": "relaxed",
        }
        return controller, transition

    def _input(self, controller, transition):
        return owner.FinalSafeWaitCompletionInput(
            continuation=controller._final_safe_wait,
            current_stage=controller.current_stage,
            safe_wait_stage=controller.STAGE_SAFE_WAIT,
            done_stage=controller.STAGE_DONE,
            active_session_generation=controller._v2_trace_started_at,
            transition=transition,
            now_s=1002.0,
            voltage_v=13.2,
            current_a=0.0,
            ah=10.0,
        )

    def test_frozen_effect_commits_one_done_edge_only_after_matching_receipt(self):
        controller, transition = self._controller()
        before_history = len(controller._stage_history)
        effect = owner.build_final_safe_wait_completion_effect(
            self._input(controller, transition)
        )
        self.assertIsNotNone(effect)
        self.assertIsInstance(effect.result, MappingProxyType)
        with self.assertRaises(TypeError):
            effect.result["turn_on"] = True

        result = controller.commit_verified_enable_transition(
            transition, now=1002.0, voltage=13.2, current=0.0, ah=10.0
        )
        self.assertEqual(controller.current_stage, controller.STAGE_DONE)
        self.assertEqual(len(controller._stage_history), before_history + 1)
        self.assertEqual(controller._stage_history[-1]["from"], controller.STAGE_SAFE_WAIT)
        self.assertEqual(controller._stage_history[-1]["to"], controller.STAGE_DONE)
        self.assertEqual(result["log_event"], "START | V2_STORAGE_OUTPUT_VERIFIED")
        self.assertIsNone(controller._final_safe_wait)

    def test_stale_or_missing_identity_is_read_only(self):
        for mutation in ("session_id", "session_generation", "started_at"):
            with self.subTest(mutation=mutation):
                controller, transition = self._controller()
                transition[mutation] = "stale" if mutation == "session_id" else -1.0
                before = (
                    controller.current_stage,
                    list(controller._stage_history),
                    controller.stage_start_time,
                    controller._final_safe_wait,
                )
                self.assertIsNone(
                    owner.build_final_safe_wait_completion_effect(
                        self._input(controller, transition)
                    )
                )
                self.assertEqual(
                    before,
                    (
                        controller.current_stage,
                        list(controller._stage_history),
                        controller.stage_start_time,
                        controller._final_safe_wait,
                    ),
                )

    def test_single_commit_applicator_has_no_physical_writer(self):
        source = inspect.getsource(owner)
        tree = ast.parse(source)
        for forbidden in ('"set_voltage"', '"set_current"', '"set_ovp"', '"set_ocp"', '"turn_on"', '"turn_off"'):
            self.assertNotIn(forbidden, source)

        controller_tree = ast.parse((ROOT / "charge_controller.py").read_text(encoding="utf-8"))
        method = next(
            node for node in ast.walk(controller_tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "commit_verified_enable_transition"
        )
        final_branch = next(
            node for node in method.body
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "kind"
            and node.test.comparators
            and isinstance(node.test.comparators[0], ast.Constant)
            and node.test.comparators[0].value == "final_safe_wait_to_done"
        )
        calls = [
            node for node in ast.walk(final_branch)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "apply_final_safe_wait_completion_effect"
        ]
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
