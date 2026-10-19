import ast
import inspect
import unittest
from pathlib import Path
from types import MappingProxyType

from charge_controller import ManagedChargeController
from runtime.charge.runtime import mix_finish_hold as owner


ROOT = Path(__file__).resolve().parents[1]


class MixFinishHoldEffectTests(unittest.TestCase):
    def test_cv_effect_is_frozen_and_preserves_evidence_payload(self):
        effect = owner.build_mix_finish_hold_effect(
            now_s=1000.0,
            is_cc=False,
            is_cv=True,
            voltage_max_v=None,
            delta_voltage_from_max_v=None,
            current_min_a=0.40,
            delta_current_from_min_a=0.10,
            session_id="session-1",
        )
        self.assertEqual(effect.mode, "CV")
        self.assertIsInstance(effect.finish_evidence, MappingProxyType)
        self.assertEqual(effect.finish_evidence["reference_value"], 0.40)
        self.assertEqual(effect.finish_evidence["accepted_delta"], 0.10)
        self.assertIn("Imin=0.400", effect.notify)
        self.assertEqual(
            effect.log_event,
            "V2_FINISH_HOLD_START | Imin=0.400А, ΔI=0.100А",
        )

    def test_cc_effect_and_applicator_preserve_state_actions(self):
        controller = ManagedChargeController(object())
        controller.start(ManagedChargeController.PROFILE_EFB, 70)
        controller._finish_evidence = None
        actions = {}
        effect = owner.build_mix_finish_hold_effect(
            now_s=2000.0,
            is_cc=True,
            is_cv=False,
            voltage_max_v=16.47,
            delta_voltage_from_max_v=0.05,
            current_min_a=None,
            delta_current_from_min_a=None,
            session_id=controller._v2_trace_session_id,
        )
        owner.apply_mix_finish_hold_effect(controller, effect, actions)
        self.assertEqual(controller.finish_timer_start, 2000.0)
        self.assertTrue(controller._delta_reported)
        self.assertEqual(controller._delta_trigger_mode, "CC")
        self.assertEqual(controller._finish_evidence["mode"], "CC")
        self.assertAlmostEqual(controller._finish_evidence["reference_value"], 16.47)
        self.assertAlmostEqual(controller._finish_evidence["accepted_delta"], 0.05)
        self.assertIn("CC", actions["notify"])
        self.assertEqual(
            actions["log_event"],
            "V2_FINISH_HOLD_START | Vmax=16.470В, ΔV=0.050В",
        )

    def test_missing_metric_keeps_hold_but_no_finish_evidence(self):
        controller = ManagedChargeController(object())
        controller.start(ManagedChargeController.PROFILE_AGM, 90)
        controller._finish_evidence = None
        effect = owner.build_mix_finish_hold_effect(
            now_s=3000.0,
            is_cc=False,
            is_cv=True,
            voltage_max_v=None,
            delta_voltage_from_max_v=None,
            current_min_a=None,
            delta_current_from_min_a=None,
            session_id=controller._v2_trace_session_id,
        )
        actions = {}
        owner.apply_mix_finish_hold_effect(controller, effect, actions)
        self.assertEqual(controller.finish_timer_start, 3000.0)
        self.assertEqual(controller._delta_trigger_mode, "CV")
        self.assertIsNone(controller._finish_evidence)
        self.assertIn("CV ΔI подтверждена", actions["notify"])

    def test_controller_has_single_effect_application_and_no_inline_hold_mutation(self):
        source = (ROOT / "charge_controller.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "apply_mix_finish_hold_effect"
        ]
        self.assertEqual(len(calls), 1)
        start = source.index("if decision.action == AuthorityAction.START_FINISH_HOLD:")
        end = source.index("elif decision.action == AuthorityAction.COMPLETE_TO_SAFE_WAIT:", start)
        branch = source[start:end]
        self.assertNotIn("self.finish_timer_start =", branch)
        self.assertNotIn("self._finish_evidence =", branch)

        owner_source = inspect.getsource(owner)
        for forbidden in ("execution_port", "set_voltage", "set_current", "turn_on", "turn_off"):
            self.assertNotIn(forbidden, owner_source)


if __name__ == "__main__":
    unittest.main()
