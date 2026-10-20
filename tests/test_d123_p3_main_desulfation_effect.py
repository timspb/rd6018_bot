"""P3-1 parity and single-owner contracts for MAIN -> DESULFATION."""

import ast
from pathlib import Path
from types import MappingProxyType
import unittest

from charge_controller import ManagedChargeController
from runtime.charge.runtime.desulfation_entry import (
    MainDesulfationEffectInput,
    apply_main_desulfation_entry,
    apply_main_desulfation_effect,
    build_main_desulfation_effect,
)
from runtime.charge.strategy.desulfation import select_desulfation_target
from runtime.charge.strategy.desulfation_variables import DESULFATION_OCP_MARGIN_A
from runtime.safety.variables import PROTECTION_OVP_MARGIN_V
from runtime.charge.runtime.variables import DELTA_MONITOR_DELAY_S

ROOT = Path(__file__).resolve().parents[1]


class MainDesulfationEffectTests(unittest.TestCase):
    def test_pure_typed_effect_preserves_action_values_for_each_profile(self):
        for profile in ("Ca/Ca", "EFB", "AGM"):
            host = ManagedChargeController(object())
            host.battery_type = profile
            host.ah_capacity = 90
            voltage, current = host._desulf_target(25.0)
            log_end = {"stage": "Main Charge", "time_sec": 60.0, "trigger": "fixture"}
            effect = build_main_desulfation_effect(MainDesulfationEffectInput(
                previous_stage=host.STAGE_MAIN,
                desulfation_stage=host.STAGE_DESULFATION,
                attempt=1,
                reason="fixture reason",
                now_s=1234.5,
                ah=4.25,
                target_voltage_v=voltage,
                target_current_a=current,
                log_event_end=log_end,
            ))
            expected = select_desulfation_target(capacity_ah=90)
            self.assertEqual((effect.target_voltage_v, effect.target_current_a),
                             (expected.voltage_v, expected.current_a))
            self.assertEqual(set(effect.action_values), {
                "log_event_end", "set_voltage", "set_current", "set_ovp",
                "set_ocp", "notify", "log_event",
            })
            self.assertEqual(effect.action_values["log_event_end"], log_end)
            self.assertEqual(effect.action_values["set_ovp"], voltage + float(PROTECTION_OVP_MARGIN_V.default))
            self.assertEqual(effect.action_values["set_ocp"], current + float(DESULFATION_OCP_MARGIN_A.default))
            self.assertEqual(effect.action_values["notify"],
                             f"🔧 <b>V2 десульфатация #1</b>\nfixture reason\nЦель: {voltage:.2f}В / {current:.2f}А на сервисный этап.")
            self.assertEqual(effect.action_values["log_event"], "START | V2_DESULFATION")
            self.assertIsInstance(effect.action_values, MappingProxyType)
            self.assertEqual(log_end, {"stage": "Main Charge", "time_sec": 60.0, "trigger": "fixture"})

    def test_single_application_commits_existing_session_state_and_no_setters(self):
        host = ManagedChargeController(object())
        host._stage_tracking_enabled = True
        host.current_stage = host.STAGE_MAIN
        host._last_transition_reason = "existing reason"
        host._restored_target_v, host._restored_target_i = 14.2, 2.0
        host.v_max_recorded, host.i_min_recorded = 15.0, 0.1
        host._delta_trigger_count = 3
        host._main_sample_evidence.plateau_since_s = 99.0
        effect = build_main_desulfation_effect(MainDesulfationEffectInput(
            previous_stage=host.current_stage, desulfation_stage=host.STAGE_DESULFATION,
            attempt=2, reason="budgeted", now_s=200.0, ah=5.0,
            target_voltage_v=15.5, target_current_a=1.8,
            log_event_end={"trigger": "budgeted"},
        ))
        actions = {}
        apply_main_desulfation_effect(host, effect, actions)
        self.assertEqual(host.current_stage, host.STAGE_DESULFATION)
        self.assertEqual(host.antisulfate_count, 2)
        self.assertEqual((host.stage_start_time, host._stage_start_ah), (200.0, 5.0))
        self.assertEqual((host._restored_target_v, host._restored_target_i), (0.0, 0.0))
        self.assertIsNone(host.v_max_recorded)
        self.assertIsNone(host.i_min_recorded)
        self.assertEqual(host._delta_trigger_count, 0)
        self.assertEqual(host._blanking_until, 200.0 + float(DELTA_MONITOR_DELAY_S.default))
        self.assertIsNone(host._main_sample_evidence.plateau_since_s)
        self.assertEqual(host._phase_current_limit, 1.8)
        self.assertEqual(len(host._stage_history), 2)
        self.assertEqual(host._stage_history[-1]["reason"], "existing reason")
        self.assertEqual(actions["set_voltage"], 15.5)
        self.assertEqual(actions["set_current"], 1.8)

    def test_controller_has_no_entry_method_and_one_effect_callsite(self):
        tree = ast.parse((ROOT / "charge_controller.py").read_text(encoding="utf-8"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ManagedChargeController")
        self.assertNotIn("_enter_desulfation", {n.name for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))})
        session = ast.parse((ROOT / "application/charge_session_tick.py").read_text(encoding="utf-8"))
        self.assertEqual(sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                             and n.func.id == "apply_charge_stage_authority" for n in ast.walk(session)), 1)
        owner_tree = ast.parse((ROOT / "runtime/charge/runtime/main_scaffold.py").read_text(encoding="utf-8"))
        self.assertEqual(sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                             and n.func.id == "apply_main_desulfation_entry"
                             for n in ast.walk(owner_tree)), 1)
        self.assertFalse(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                             and n.func.id in {"MainDesulfationEffectInput", "build_main_desulfation_effect",
                                               "apply_main_desulfation_effect"}
                             for n in ast.walk(tree)))
        owner = ast.parse((ROOT / "runtime/charge/runtime/desulfation_entry.py").read_text(encoding="utf-8"))
        for node in ast.walk(owner):
            if isinstance(node, ast.ImportFrom):
                self.assertFalse((node.module or "").endswith("charge_controller"))

    def test_bounded_dispatch_preserves_profile_target_and_event_end(self):
        for profile in ("Ca/Ca", "EFB", "AGM"):
            with self.subTest(profile=profile):
                host = ManagedChargeController(object())
                host.battery_type, host.ah_capacity = profile, 90
                host._make_log_event_end = lambda *args: {"trigger": args[-1]}
                voltage, current = host._desulf_target(25.0)
                actions = {}
                apply_main_desulfation_entry(
                    host, reason="fixture", now_s=123.0, ah=4.0, voltage_v=14.0,
                    current_a=1.0, temperature_c=25.0, target_voltage_v=voltage,
                    target_current_a=current, actions=actions,
                )
                self.assertEqual((actions["set_voltage"], actions["set_current"]),
                                 (voltage, current))
                self.assertEqual(actions["log_event_end"], {"trigger": "fixture"})
                self.assertEqual(host.antisulfate_count, 1)

    def test_event_end_failure_precedes_mutation_and_action_application(self):
        host = ManagedChargeController(object())
        host.current_stage = host.STAGE_MAIN
        host.antisulfate_count = 2
        host._make_log_event_end = lambda *args: (_ for _ in ()).throw(RuntimeError("capture"))
        actions = {"existing": True}
        with self.assertRaisesRegex(RuntimeError, "capture"):
            apply_main_desulfation_entry(
                host, reason="fixture", now_s=123.0, ah=4.0, voltage_v=14.0,
                current_a=1.0, temperature_c=25.0, target_voltage_v=15.5,
                target_current_a=1.8, actions=actions,
            )
        self.assertEqual(host.current_stage, host.STAGE_MAIN)
        self.assertEqual(host.antisulfate_count, 2)
        self.assertEqual(actions, {"existing": True})


if __name__ == "__main__":
    unittest.main()
