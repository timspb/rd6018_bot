import ast
import unittest
from pathlib import Path

from charge_controller import ManagedChargeController
from runtime.charge.runtime import final_safe_wait_authority as owner
from runtime.charge.strategy.final_safe_wait import FinalSafeWaitContinuation


ROOT = Path(__file__).resolve().parents[1]


class FinalSafeWaitAuthorityEffectTests(unittest.TestCase):
    def setUp(self):
        self.continuation = FinalSafeWaitContinuation(
            source_stage=ManagedChargeController.STAGE_MIX,
            next_stage=ManagedChargeController.STAGE_DONE,
            target_voltage_v=13.8,
            target_current_a=1.0,
            started_at=100.0,
            session_id="session",
            completion_reason="confirmed_delta_finish_hold_complete",
            session_generation=90.0,
        )

    def build(self, **kwargs):
        values = dict(
            continuation=self.continuation,
            current_stage=ManagedChargeController.STAGE_SAFE_WAIT,
            safe_wait_stage=ManagedChargeController.STAGE_SAFE_WAIT,
            done_stage=ManagedChargeController.STAGE_DONE,
            session_id="session",
            session_generation=90.0,
            allowed_source_stages={ManagedChargeController.STAGE_MAIN, ManagedChargeController.STAGE_MIX},
            now_s=200.0,
            voltage_v=13.0,
            output_is_off=True,
            add_phase_limits=lambda actions, voltage, current: actions.update(set_ovp=16.0, set_ocp=5.0),
        )
        values.update(kwargs)
        return owner.build_final_safe_wait_authority_effect(**values)

    def test_storage_request_effect_preserves_exact_action_values(self):
        effect = self.build()
        self.assertEqual(effect.decision.reason, "threshold")
        self.assertEqual(dict(effect.actions), {
            "set_voltage": 13.8,
            "set_current": 1.0,
            "set_ovp": 16.0,
            "set_ocp": 5.0,
            "turn_on": True,
            "verified_enable_transition": {
                "kind": "final_safe_wait_to_done",
                "session_id": "session",
                "session_generation": 90.0,
                "started_at": 100.0,
                "reason": "threshold",
            },
            "log_event": "FINAL_SAFE_WAIT_STORAGE_ENABLE_ATTEMPT",
        })
        with self.assertRaises(TypeError):
            effect.actions["turn_on"] = False

    def test_wait_has_no_action_and_invalid_identity_is_rejected(self):
        wait = self.build(output_is_off=False)
        self.assertEqual(wait.decision.reason, "fresh_output_off_required")
        self.assertEqual(dict(wait.actions), {})
        self.assertIsNone(self.build(session_generation=89.0))

    def test_runtime_owner_applies_effect_once_and_controller_has_no_duplicate(self):
        tree = ast.parse((ROOT / "runtime/charge/runtime/final_safe_wait_authority.py").read_text(encoding="utf-8"))
        method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "apply_final_safe_wait_authority")
        calls = [node for node in ast.walk(method) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "build_final_safe_wait_authority_effect"]
        self.assertEqual(len(calls), 1)
        controller_tree = ast.parse((ROOT / "charge_controller.py").read_text(encoding="utf-8"))
        self.assertFalse(any(isinstance(node, ast.FunctionDef) and node.name == "_apply_final_safe_wait_authority" for node in ast.walk(controller_tree)))


if __name__ == "__main__":
    unittest.main()
