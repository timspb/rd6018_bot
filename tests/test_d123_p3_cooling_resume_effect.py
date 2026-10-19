from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path
from types import MappingProxyType

from charge_controller import ManagedChargeController
from runtime.charge.runtime import cooling_resume as owner


ROOT = Path(__file__).resolve().parents[1]


class CoolingResumeEffectTests(unittest.TestCase):
    def _effect(self):
        host = ManagedChargeController(object())
        return owner.build_cooling_resume_effect(owner.CoolingResumeInput(
            source_stage=host.STAGE_COOLING, return_stage=host.STAGE_PREP, cooling_stage=host.STAGE_COOLING,
            now_s=1200, ah=2, target_voltage_v=12.0, target_current_a=0.6,
            blanking_seconds=30, battery_capacity_ah=60, warning_temperature_c=35,
            temperature_c=35, actions={"log_event_end": {"stage": "COOLING"}, "set_ovp": 12.1, "set_ocp": 0.7},
        ))

    def test_frozen_effect_preserves_resume_action_and_timing_values(self):
        effect = self._effect()
        self.assertIsInstance(effect.action_values, MappingProxyType)
        self.assertIsInstance(effect.action_values["log_event_end"], MappingProxyType)
        self.assertEqual(effect.action_values["set_voltage"], 12.0)
        self.assertEqual(effect.action_values["set_current"], 0.6)
        self.assertEqual(effect.action_values["set_ovp"], 12.1)
        self.assertEqual(effect.action_values["set_ocp"], 0.7)
        self.assertTrue(effect.action_values["turn_on"])
        with self.assertRaises(TypeError):
            effect.action_values["turn_on"] = False

    def test_applicator_commits_one_cooling_resume_edge_and_rejects_stale_stage(self):
        host = ManagedChargeController(object())
        host.start(host.PROFILE_EFB, 60)
        host.current_stage = host.STAGE_COOLING
        host._cooling_from_stage = host.STAGE_PREP
        host._cooling_target_v, host._cooling_target_i = 12.0, 0.6
        before = len(host._stage_history)
        actions = {"retained": 1}
        self.assertTrue(owner.apply_cooling_resume_effect(host, self._effect(), actions))
        self.assertEqual(host.current_stage, host.STAGE_PREP)
        self.assertEqual(len(host._stage_history), before + 1)
        self.assertEqual(host.stage_start_time, 1200)
        self.assertEqual(host._stage_start_ah, 2)
        self.assertIsNone(host._cooling_from_stage)
        self.assertEqual(host._blanking_until, 1230)
        self.assertTrue(actions["turn_on"])
        self.assertEqual(actions["retained"], 1)

        host.current_stage = host.STAGE_PREP
        before = len(host._stage_history)
        self.assertFalse(owner.apply_cooling_resume_effect(host, self._effect(), {}))
        self.assertEqual(len(host._stage_history), before)

    def test_single_residual_applicator_call_and_no_physical_writer_in_owner(self):
        source = (ROOT / "runtime/charge/runtime/residual_scaffold.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id == "apply_cooling_resume_effect"]
        self.assertEqual(len(calls), 1)
        owner_source = inspect.getsource(owner)
        owner_tree = ast.parse(owner_source)
        attributes = [node.func.attr for node in ast.walk(owner_tree)
                      if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
        for forbidden in ("set_voltage", "set_current", "set_ovp", "set_ocp", "turn_on", "turn_off"):
            self.assertNotIn(forbidden, attributes)
        self.assertNotIn("execution_port", owner_source)


if __name__ == "__main__":
    unittest.main()
