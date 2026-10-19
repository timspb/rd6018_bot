from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path

from runtime.charge.runtime import residual_terminal as owner
from runtime.charge.runtime import residual_observation
from runtime.charge.runtime import residual_reporting


ROOT = Path(__file__).resolve().parents[1]


class ResidualTerminalDecisionTests(unittest.TestCase):
    def test_reporting_effect_preserves_pending_log_and_hourly_report_parity(self):
        class Host:
            _pending_log_event = "WARNING_35C"
            _last_hourly_report = 100.0
            notices = []

            def notify(self, value):
                self.notices.append(value)

        host = Host()
        actions = {"notify": "existing warning"}
        effect = residual_reporting.build_residual_reporting_effect(
            pending_log_event=host._pending_log_event,
            manual_off_active=False, now_s=3700.0, last_hourly_report_s=100.0,
            report_interval_s=3600.0, elapsed_s=3600.0, current_a=1.25,
            temperature_c=26.0, ah=3.5, existing_notify=actions["notify"],
        )
        self.assertTrue(effect.consume_pending_log)
        self.assertEqual(effect.pending_log_event, "WARNING_35C")
        self.assertEqual(effect.last_hourly_report_s, 3700.0)
        self.assertEqual(
            effect.report_text,
            "⏳ Прошло 1.0ч из — лимита этапа. Ток: 1.25 А, T: 26.0°C, Ah: 3.50.",
        )
        residual_reporting.apply_residual_reporting_effect(host, effect, actions)
        self.assertEqual(actions["log_event"], "WARNING_35C")
        self.assertIsNone(host._pending_log_event)
        self.assertEqual(host._last_hourly_report, 3700.0)
        self.assertEqual(host.notices, [effect.report_text])
        self.assertEqual(actions["notify"], "existing warning")

    def test_reporting_effect_respects_manual_off_and_empty_notify(self):
        class Host:
            _pending_log_event = None
            _last_hourly_report = 10.0
            def notify(self, value):
                raise AssertionError("empty notify should be filled in actions")

        host = Host()
        actions = {"notify": ""}
        manual = residual_reporting.build_residual_reporting_effect(
            pending_log_event=None, manual_off_active=True, now_s=5000.0,
            last_hourly_report_s=10.0, report_interval_s=60.0, elapsed_s=0.0,
            current_a=0.0, temperature_c=20.0, ah=0.0, existing_notify="",
        )
        residual_reporting.apply_residual_reporting_effect(host, manual, actions)
        self.assertIsNone(manual.report_text)
        self.assertEqual(host._last_hourly_report, 10.0)
        self.assertEqual(actions["notify"], "")

        report = residual_reporting.build_residual_reporting_effect(
            pending_log_event=None, manual_off_active=False, now_s=5000.0,
            last_hourly_report_s=10.0, report_interval_s=60.0, elapsed_s=0.0,
            current_a=0.0, temperature_c=20.0, ah=0.0, existing_notify="",
        )
        residual_reporting.apply_residual_reporting_effect(host, report, actions)
        self.assertEqual(actions["notify"], report.report_text)

    def test_reporting_owner_is_frozen_single_call_and_has_no_writer(self):
        effect = residual_reporting.build_residual_reporting_effect(
            pending_log_event=None, manual_off_active=False, now_s=0,
            last_hourly_report_s=0, report_interval_s=60, elapsed_s=0,
            current_a=0, temperature_c=20, ah=0, existing_notify=None,
        )
        with self.assertRaises((AttributeError, TypeError)):
            effect.report_text = "changed"
        source = (ROOT / "runtime/charge/runtime/residual_scaffold.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name)
                 and node.func.id == "apply_residual_reporting_effect"]
        self.assertEqual(len(calls), 1)
        scaffold_writes = {
            (target.attr, node.value.value if isinstance(node.value, ast.Constant) else object())
            for node in ast.walk(tree)
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign))
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
            and target.value.id == "host"
        }
        self.assertNotIn(("_pending_log_event", None), scaffold_writes)
        self.assertFalse(any(name == "_last_hourly_report" for name, _ in scaffold_writes))
        owner_source = inspect.getsource(residual_reporting)
        self.assertNotIn("execution_port", owner_source)
        self.assertNotIn("set_voltage", owner_source)
        self.assertNotIn("turn_on", owner_source)

    def test_reporting_failure_preserves_pre_notify_state_commit_order(self):
        class Host:
            _pending_log_event = "PENDING"
            _last_hourly_report = 0.0

            def notify(self, value):
                raise RuntimeError("synthetic notification failure")

        host = Host()
        actions = {"notify": "existing"}
        effect = residual_reporting.build_residual_reporting_effect(
            pending_log_event=host._pending_log_event, manual_off_active=False,
            now_s=100.0, last_hourly_report_s=0.0, report_interval_s=60.0,
            elapsed_s=90.0, current_a=1.0, temperature_c=25.0, ah=2.0,
            existing_notify=actions["notify"],
        )
        with self.assertRaisesRegex(RuntimeError, "synthetic notification failure"):
            residual_reporting.apply_residual_reporting_effect(host, effect, actions)
        self.assertIsNone(host._pending_log_event)
        self.assertEqual(host._last_hourly_report, 100.0)
        self.assertEqual(actions["log_event"], "PENDING")

    def test_terminal_observation_mutation_has_evidence_owner_and_parity(self):
        class Host:
            STAGE_IDLE = "IDLE"

            def __init__(self):
                self._stage_start_voltage = 0.0
                self._stage_start_current = 0.0
                self._stage_start_temp = 0.0
                self._last_voltage = self._last_current = self._last_temp_ext = self._last_ah = 0.0
                self._analytics_history = []
                self._last_v_i_history_time = 0.0
                self.v_history, self.i_history = [], []

        idle = Host()
        residual_observation.record_residual_observation(
            idle, stage="IDLE", timestamp_s=61, voltage_v=12.4, current_a=0.2,
            temperature_c=23, ah=1.5, history_interval_s=60,
        )
        self.assertEqual((idle._last_voltage, idle._last_current, idle._last_ah), (12.4, 0.2, 1.5))
        self.assertEqual(idle._analytics_history, [])
        self.assertEqual((idle.v_history, idle.i_history), ([], []))

        done = Host()
        residual_observation.record_residual_observation(
            done, stage="DONE", timestamp_s=61, voltage_v=12.5, current_a=0.1,
            temperature_c=24, ah=2.0, history_interval_s=60,
        )
        self.assertEqual(done._analytics_history, [(61, 12.5, 0.1, 2.0, 24)])
        self.assertEqual(done.v_history, [(61, 12.5)])
        self.assertEqual(done.i_history, [(61, 0.1)])
        self.assertEqual(done._stage_start_voltage, 12.5)

    def test_residual_scaffold_uses_observation_owner_once(self):
        source = (ROOT / "runtime/charge/runtime/residual_scaffold.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id == "record_residual_observation"]
        self.assertEqual(len(calls), 1)
        self.assertNotIn("host._analytics_history.append", source)
        self.assertNotIn("host._mark_stage_sample", source)
        owner_source = inspect.getsource(residual_observation)
        self.assertNotIn("execution_port", owner_source)
        self.assertNotIn("set_voltage", owner_source)
        self.assertNotIn("turn_on", owner_source)

    def test_idle_and_done_keep_distinct_return_semantics(self):
        idle = owner.decide_residual_terminal("IDLE", idle_stage="IDLE", done_stage="DONE")
        done = owner.decide_residual_terminal("DONE", idle_stage="IDLE", done_stage="DONE")
        self.assertTrue(idle.return_after_observation)
        self.assertFalse(done.return_after_observation)

    def test_nonterminal_and_unknown_stages_are_rejected(self):
        for stage in ("PREP", "COOLING", "UNKNOWN"):
            with self.subTest(stage=stage), self.assertRaises(ValueError):
                owner.decide_residual_terminal(stage, idle_stage="IDLE", done_stage="DONE")

    def test_residual_scaffold_routes_terminal_policy_through_single_owner(self):
        source = (ROOT / "runtime/charge/runtime/residual_scaffold.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id == "decide_residual_terminal"]
        self.assertEqual(len(calls), 1)
        self.assertIn("terminal.return_after_observation", source)
        self.assertIn("DONE has no automatic transition", source)
        owner_source = inspect.getsource(owner)
        owner_tree = ast.parse(owner_source)
        setters = [node.func.attr for node in ast.walk(owner_tree)
                   if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
        self.assertFalse(set(setters) & {"set_voltage", "set_current", "set_ovp", "set_ocp", "turn_on", "turn_off"})
        self.assertNotIn("execution_port", owner_source)


if __name__ == "__main__":
    unittest.main()
