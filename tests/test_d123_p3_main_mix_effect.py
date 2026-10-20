"""P3-3 parity and ownership gates for the existing MAIN-to-MIX effect."""

import ast
from pathlib import Path
import unittest

from charge_controller import ManagedChargeController
from runtime.charge.runtime.mix_entry import (
    MainMixEffectInput, apply_main_mix_effect, apply_main_mix_entry,
    build_main_mix_effect,
)
from runtime.charge.runtime.variables import DELTA_MONITOR_DELAY_S

ROOT = Path(__file__).resolve().parents[1]


class MainMixEffectTests(unittest.TestCase):
    def test_effect_preserves_profile_target_actions_and_single_stage_edge(self):
        for profile in ("Ca/Ca", "EFB", "AGM"):
            with self.subTest(profile=profile):
                host = ManagedChargeController(object())
                host.battery_type, host.ah_capacity = profile, 90
                host._stage_tracking_enabled = True
                host.current_stage = host.STAGE_MAIN
                host._last_transition_reason = "existing reason"
                host._restored_target_v, host._restored_target_i = 13.9, 2.0
                host.v_max_recorded, host.i_min_recorded = 15.0, 0.2
                host.finish_timer_start = 50.0
                host._delta_reported = True
                host._main_sample_evidence.plateau_since_s = 10.0
                voltage, current = host._mix_target(25.0)
                actions = {}
                host._add_phase_limits(actions, voltage, current)
                ovp, ocp = actions["set_ovp"], actions["set_ocp"]
                effect = build_main_mix_effect(MainMixEffectInput(
                    host.STAGE_MAIN, host.STAGE_MIX, "fixture", 1234.0, 4.5,
                    voltage, current, ovp, ocp,
                    {"stage": host.STAGE_MAIN, "trigger": "fixture"},
                ))
                applied = {}
                apply_main_mix_effect(host, effect, applied)
                self.assertEqual(set(applied), {
                    "log_event_end", "set_voltage", "set_current", "set_ovp",
                    "set_ocp", "notify", "log_event",
                })
                self.assertEqual((applied["set_voltage"], applied["set_current"],
                                  applied["set_ovp"], applied["set_ocp"]),
                                 (voltage, current, ovp, ocp))
                self.assertEqual(applied["log_event"], "START | V2_MIX")
                self.assertIn("выход по CV ΔI или CC ΔV", applied["notify"])
                self.assertEqual(host.current_stage, host.STAGE_MIX)
                self.assertEqual(len(host._stage_history), 2)
                self.assertEqual(host._stage_history[-1]["reason"], "existing reason")
                self.assertEqual((host.stage_start_time, host._stage_start_ah), (1234.0, 4.5))
                self.assertEqual((host._restored_target_v, host._restored_target_i), (0.0, 0.0))
                self.assertEqual(host._blanking_until, 1234.0 + float(DELTA_MONITOR_DELAY_S.default))
                self.assertIsNone(host.v_max_recorded)
                self.assertIsNone(host.i_min_recorded)
                self.assertIsNone(host.finish_timer_start)
                self.assertFalse(host._delta_reported)
                self.assertIsNone(host._main_sample_evidence.plateau_since_s)

    def test_controller_has_one_caller_and_effect_has_no_actuator_or_controller_import(self):
        tree = ast.parse((ROOT / "application/charge_session_tick.py").read_text(encoding="utf-8"))
        controller_source = (ROOT / "charge_controller.py").read_text(encoding="utf-8")
        self.assertNotIn("def _enter_mix(", controller_source)
        for name in ("apply_charge_stage_authority",):
            self.assertEqual(sum(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                                 and node.func.id == name for node in ast.walk(tree)), 1)
        owner_tree = ast.parse((ROOT / "runtime/charge/runtime/main_scaffold.py").read_text(encoding="utf-8"))
        self.assertEqual(sum(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                             and node.func.id == "apply_main_mix_entry"
                             for node in ast.walk(owner_tree)), 1)
        self.assertFalse(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                             and node.func.id in {"MainMixEffectInput", "build_main_mix_effect",
                                                  "apply_main_mix_effect"}
                             for node in ast.walk(tree)))
        owner = ast.parse((ROOT / "runtime/charge/runtime/mix_entry.py").read_text(encoding="utf-8"))
        for node in ast.walk(owner):
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn("charge_controller", node.module or "")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr.lower(), {"set_voltage", "set_current", "set_output", "turn_on"})

    def test_bounded_dispatch_preserves_profile_target_limits_and_event_end(self):
        for profile in ("Ca/Ca", "EFB", "AGM"):
            with self.subTest(profile=profile):
                host = ManagedChargeController(object())
                host.battery_type, host.ah_capacity = profile, 90
                host._make_log_event_end = lambda *args: {"trigger": args[-1]}
                voltage, current = host._mix_target(25.0)
                limits = {}
                host._add_phase_limits(limits, voltage, current)
                actions = {}
                apply_main_mix_entry(
                    host, reason="fixture", now_s=123.0, ah=4.0, voltage_v=14.0,
                    current_a=1.0, temperature_c=25.0, target_voltage_v=voltage,
                    target_current_a=current, ovp_v=limits["set_ovp"],
                    ocp_a=limits["set_ocp"], actions=actions,
                )
                self.assertEqual((actions["set_voltage"], actions["set_current"],
                                  actions["set_ovp"], actions["set_ocp"]),
                                 (voltage, current, limits["set_ovp"], limits["set_ocp"]))
                self.assertEqual(actions["log_event_end"], {"trigger": "fixture"})
                self.assertEqual(host.current_stage, host.STAGE_MIX)

    def test_event_end_failure_precedes_mutation_and_action_application(self):
        host = ManagedChargeController(object())
        host.current_stage = host.STAGE_MAIN
        host._make_log_event_end = lambda *args: (_ for _ in ()).throw(RuntimeError("capture"))
        actions = {"existing": True}
        with self.assertRaisesRegex(RuntimeError, "capture"):
            apply_main_mix_entry(
                host, reason="fixture", now_s=123.0, ah=4.0, voltage_v=14.0,
                current_a=1.0, temperature_c=25.0, target_voltage_v=15.5,
                target_current_a=2.0, ovp_v=16.0, ocp_a=3.0, actions=actions,
            )
        self.assertEqual(host.current_stage, host.STAGE_MAIN)
        self.assertEqual(actions, {"existing": True})


if __name__ == "__main__":
    unittest.main()
