import ast
from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest
from types import SimpleNamespace

from runtime.charge.evidence.trace_context import (
    SignalContextInput,
    TracePointInput,
    build_shadow_metadata,
    build_signal_context,
    build_trace_point_metadata,
)
from signal_analyzer import SignalEvent, SignalMetrics
from pb_domain import BatteryCondition, ChargeIntent


ROOT = Path(__file__).resolve().parents[1]


class TraceContextEvidenceTests(unittest.TestCase):
    def test_cv_signal_context_keeps_imin_and_current_delta_references(self):
        metrics = SignalMetrics(
            d_voltage_v_per_min=0.01, d_current_a_per_min=0.02,
            d_temp_c_per_min=0.0, current_min_a=0.4,
            seconds_since_current_min=30.0, delta_current_from_min_a=0.1,
            reversal_threshold_a=0.08, current_plateau_span_a=0.03,
            current_plateau_center_a=0.5, reversal_confirmations=2,
            voltage_max_v=14.8, seconds_since_voltage_max=40.0,
            delta_voltage_from_max_v=-0.01,
            voltage_reversal_threshold_v=0.03,
            voltage_reversal_confirmations=0,
        )
        analyzer = SimpleNamespace(
            _current_min_time_s=970.0, _voltage_max_time_s=960.0,
            _last_reversal_confirmation_s=995.0, _reversal_emitted=False,
            _last_voltage_reversal_confirmation_s=None,
            _voltage_reversal_emitted=False,
        )
        context = build_signal_context(SignalContextInput(
            stage="Main Charge", mode="CV", session_id="sid",
            session_generation=900.0, output_is_on="on", is_cv=True,
            is_cc=False, telemetry_valid=True, timestamp_s=1000.0,
            now_s=1002.0, target_voltage_v=14.8, metrics=metrics,
            analyzer=analyzer,
        ))
        self.assertEqual(context["mode"], "CV")
        self.assertEqual(context["current_min_a"], 0.4)
        self.assertEqual(context["current_min_time_s"], 30.0)
        self.assertEqual(context["delta_reference_a"], 0.4)
        self.assertEqual(context["telemetry_age_s"], 2.0)
        self.assertTrue(context["output_on"])

    def test_cc_signal_context_keeps_vmax_and_voltage_confirmation(self):
        metrics = SignalMetrics(
            d_voltage_v_per_min=-0.02, d_current_a_per_min=0.0,
            d_temp_c_per_min=0.0, current_min_a=None,
            seconds_since_current_min=None, delta_current_from_min_a=None,
            reversal_threshold_a=None, current_plateau_span_a=None,
            current_plateau_center_a=None, reversal_confirmations=0,
            voltage_max_v=16.4, seconds_since_voltage_max=20.0,
            delta_voltage_from_max_v=-0.08,
            voltage_reversal_threshold_v=0.05,
            voltage_reversal_confirmations=2,
        )
        analyzer = SimpleNamespace(
            _current_min_time_s=None, _voltage_max_time_s=980.0,
            _last_reversal_confirmation_s=None, _reversal_emitted=False,
            _last_voltage_reversal_confirmation_s=995.0,
            _voltage_reversal_emitted=True,
        )
        context = build_signal_context(SignalContextInput(
            stage="Mix Mode", mode="CC", session_id="sid", session_generation=900,
            output_is_on=True, is_cv=False, is_cc=True, telemetry_valid=True,
            timestamp_s=1000.0, now_s=999.0, target_voltage_v=16.4,
            metrics=metrics, analyzer=analyzer,
        ))
        self.assertEqual(context["mode"], "CC")
        self.assertEqual(context["voltage_max_v"], 16.4)
        self.assertEqual(context["voltage_max_time_s"], 20.0)
        self.assertEqual(context["delta_reference_v"], 16.4)
        self.assertEqual(context["voltage_reversal_confirmations"], 2)
        self.assertTrue(context["voltage_reversal_emitted"])
        self.assertEqual(context["telemetry_age_s"], 0.0)

    def test_trace_and_event_metadata_keep_stable_payload_keys(self):
        point = build_trace_point_metadata(TracePointInput(
            timestamp_s=12, stage_before="Mix Mode", stage_after="Safe Wait",
            target_before=16.5, voltage="nan", current="0.4", temp_ext=None,
            is_cv=True, is_cc=False, ah="2.0", output_is_on="unknown",
        ))
        self.assertEqual(point, {
            "timestamp_s": 12.0, "stage": "Mix Mode",
            "legacy_stage_after": "Safe Wait", "voltage_v": None,
            "current_a": 0.4, "temp_c": None, "is_cv": True,
            "is_cc": False, "target_voltage_v": 16.5, "ah": 2.0,
            "output_on": None,
        })
        metrics = SignalMetrics(
            d_voltage_v_per_min=None, d_current_a_per_min=None,
            d_temp_c_per_min=None, current_min_a=0.4,
            seconds_since_current_min=10, delta_current_from_min_a=0.1,
            reversal_threshold_a=0.08, current_plateau_span_a=None,
            current_plateau_center_a=None, reversal_confirmations=2,
            voltage_max_v=16.4, seconds_since_voltage_max=10,
            delta_voltage_from_max_v=-0.1, voltage_reversal_threshold_v=0.05,
            voltage_reversal_confirmations=2,
        )
        record = SimpleNamespace(
            analysis=SimpleNamespace(metrics=metrics, events=frozenset({
                SignalEvent.CURRENT_REVERSAL_CONFIRMED,
                SignalEvent.VOLTAGE_REVERSAL_CONFIRMED,
            })),
            decision=SimpleNamespace(
                decision=SimpleNamespace(value="continue"), reason="evidence_observed"
            ),
            disagreement=None, legacy_effect="continue",
        )
        payload = build_shadow_metadata(record, trace_point=point)
        self.assertEqual(payload["events"], sorted([
            SignalEvent.CURRENT_REVERSAL_CONFIRMED.value,
            SignalEvent.VOLTAGE_REVERSAL_CONFIRMED.value,
        ]))
        self.assertEqual(payload["trace_point"], point)
        self.assertEqual(payload["metrics"]["voltage_reversal_confirmations"], 2)

    def test_controller_has_no_duplicated_assembly_implementation_or_call_path(self):
        source = (ROOT / "charge_controller.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                   and node.name == "ManagedChargeController")
        method_names = {node.name for node in cls.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        moved = {
            "_trace_point_metadata", "_shadow_metadata", "_first_stage_metadata",
            "_finite_or_none", "_finite_or_nan", "_normalize_output_on",
        }
        self.assertTrue(moved.isdisjoint(method_names))
        calls = [node for node in ast.walk(cls) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name)
                 and node.func.id == "build_signal_context"]
        self.assertEqual(len(calls), 0)
        tick = next(node for node in cls.body if isinstance(node, ast.AsyncFunctionDef)
                    and node.name == "tick")
        tick_assembly_calls = [node for node in ast.walk(tick) if isinstance(node, ast.Call)
                               and isinstance(node.func, ast.Name)
                               and node.func.id in {"build_signal_context", "build_trace_point_metadata", "build_shadow_metadata"}]
        self.assertEqual(tick_assembly_calls, [])
        owner = ast.parse((ROOT / "application/charge_session_tick.py").read_text(encoding="utf-8"))
        owner_calls = [node for node in ast.walk(owner) if isinstance(node, ast.Call)
                       and isinstance(node.func, ast.Name)
                       and node.func.id in {"build_signal_context", "build_trace_point_metadata", "build_shadow_metadata"}]
        self.assertEqual(sum(node.func.id == "build_signal_context" for node in owner_calls), 1)
        self.assertEqual(sum(node.func.id == "build_trace_point_metadata" for node in owner_calls), 2)
        self.assertEqual(sum(node.func.id == "build_shadow_metadata" for node in owner_calls), 1)

    def test_trace_lifecycle_is_owned_outside_controller_and_store_is_single_writer(self):
        source = (ROOT / "charge_controller.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                   and node.name == "ManagedChargeController")
        names = {node.name for node in cls.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.assertTrue({"_persist_shadow_trace_if_ready", "_log_shadow_disagreement"}.isdisjoint(names))
        self.assertNotIn("_v2_last_disagreement", source)
        self.assertNotIn("_v2_disagreement_repeat_count", source)
        definitions = []
        for path in ROOT.rglob("*.py"):
            module = ast.parse(path.read_text(encoding="utf-8"))
            definitions.extend((path.name, node.name) for node in ast.walk(module)
                               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                               and node.name == "record_shadow_trace")
        self.assertEqual(definitions, [("recovery_trace_store.py", "record_shadow_trace")])

    def test_non_authoritative_snapshot_is_explicitly_diagnostic(self):
        source = (ROOT / "charge_controller.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                      and node.name == "signal_analyzer_diagnostic_snapshot")
        self.assertIn("non-authoritative analyzer diagnostic snapshot", ast.get_docstring(method))
        self.assertNotIn("signal_analyzer_diagnostic_snapshot", {
            node.id for node in ast.walk(method) if isinstance(node, ast.Name)
        })
        self.assertFalse({"set_output", "safe_enable_output", "turn_on"} & {
            node.id for node in ast.walk(method) if isinstance(node, ast.Name)
        })

    def test_disagreement_throttle_logs_once_then_every_twentieth_repeat(self):
        from unittest.mock import patch
        from runtime.charge.evidence.trace_context import TraceLifecycle
        lifecycle = TraceLifecycle()
        record = SimpleNamespace(
            disagreement="stage_mismatch",
            decision=SimpleNamespace(decision=SimpleNamespace(value="continue"), reason="test"),
            legacy_effect="hold",
        )
        with patch("runtime.charge.evidence.trace_context.logger.warning") as warning:
            for _ in range(19):
                lifecycle.observe_disagreement(record, stage="MAIN")
            self.assertEqual(warning.call_count, 1)
            lifecycle.observe_disagreement(record, stage="MAIN")
            self.assertEqual(warning.call_count, 2)
        self.assertEqual(lifecycle.disagreement_repeat_count, 20)

    def test_recovery_context_keeps_fallback_enum_identity_and_is_frozen(self):
        from runtime.charge.evidence.trace_context import recovery_trace_context
        host = SimpleNamespace(
            _v2_trace_started_at=1200.125, total_start_time=999.0,
            _v2_battery_id=None, battery_type="EFB", ah_capacity=70,
            _v2_trace_session_id=None, _v2_intent=ChargeIntent.RECOVERY,
            _v2_condition_before=BatteryCondition.UNKNOWN,
        )
        context = recovery_trace_context(host)
        seed = "anonymous:EFB:70|EFB|70|1200.125000"
        expected_id = __import__("uuid").uuid5(
            __import__("uuid").NAMESPACE_URL, f"rd6018-volatile:{seed}"
        ).hex
        self.assertEqual(context.session_id, expected_id)
        self.assertEqual(context.started_at, 1200.125)
        self.assertIs(context.intent, ChargeIntent.RECOVERY)
        self.assertIs(context.condition_before, BatteryCondition.UNKNOWN)
        with self.assertRaises(FrozenInstanceError):
            context.started_at = 1.0
        signal_input = SignalContextInput(
            stage="MAIN", mode="CV", session_id=context.session_id,
            session_generation=context.started_at, output_is_on=True, is_cv=True,
            is_cc=False, telemetry_valid=True, timestamp_s=1201.0, now_s=1201.0,
            target_voltage_v=14.8, metrics=SimpleNamespace(),
        )
        with self.assertRaises(FrozenInstanceError):
            signal_input.stage = "MIX"


if __name__ == "__main__":
    unittest.main()
