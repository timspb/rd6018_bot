"""Fake-only characterization of Manual delta, MAIN tail, and MIX hold methods."""

import ast
import logging
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

from application.manual_observer_use_case import MANUAL_MIX_FINISH_HOLD_SEC
from application.manual_phase_evidence import (
    evaluate_manual_main_tail,
    evaluate_manual_mix_hold,
)
from runtime.charge.evidence.manual_delta import (
    MANUAL_DELTA_BLANKING_SEC,
    MANUAL_DELTA_CONFIRM_COUNT,
    MANUAL_DELTA_CONFIRM_INTERVAL_SEC,
    ManualDeltaEvidencePolicy,
    ManualDeltaEvidenceState,
    ManualDeltaSample,
    evaluate_manual_delta_evidence,
)
from runtime.charge.evidence.first_stage_variables import (
    MANUAL_DEFAULT_MAIN_TAIL_CURRENT_A as MANUAL_DEFAULT_MAIN_TAIL_CURRENT_SPEC,
)
from runtime.charge.strategy.manual_phase_lifecycle import manual_mix_finish_hold_complete


SOURCE_PATH = Path(__file__).resolve().parents[1] / "manual_mode.py"


def _load_actual_methods():
    tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))
    manager = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ManualSessionManager"
    )
    methods = [node for node in manager.body if isinstance(node, ast.FunctionDef) and node.name == "_delta_reason"]
    if len(methods) != 1:
        raise AssertionError("ManualSessionManager delta method was not found")
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in {
                "MANUAL_DELTA_BLANKING_SEC", "MANUAL_DELTA_CONFIRM_COUNT",
                "MANUAL_DELTA_CONFIRM_INTERVAL_SEC", "MANUAL_DEFAULT_MAIN_TAIL_CURRENT_A",
            }:
                if node.targets[0].id == "MANUAL_DEFAULT_MAIN_TAIL_CURRENT_A":
                    constants[node.targets[0].id] = float(MANUAL_DEFAULT_MAIN_TAIL_CURRENT_SPEC.default)
                else:
                    constants[node.targets[0].id] = ast.literal_eval(node.value)
    namespace = {
        **constants,
        "Any": Any,
        "Optional": Optional,
        "MANUAL_DELTA_BLANKING_SEC": MANUAL_DELTA_BLANKING_SEC,
        "MANUAL_DELTA_CONFIRM_COUNT": MANUAL_DELTA_CONFIRM_COUNT,
        "MANUAL_DELTA_CONFIRM_INTERVAL_SEC": MANUAL_DELTA_CONFIRM_INTERVAL_SEC,
        "ManualDeltaEvidencePolicy": ManualDeltaEvidencePolicy,
        "ManualDeltaEvidenceState": ManualDeltaEvidenceState,
        "ManualDeltaSample": ManualDeltaSample,
        "evaluate_manual_delta_evidence": evaluate_manual_delta_evidence,
    }
    isolated = ast.Module(body=methods, type_ignores=[])
    exec(compile(ast.fix_missing_locations(isolated), str(SOURCE_PATH), "exec"), namespace)
    return namespace


_METHODS = _load_actual_methods()


class ManualEvidenceState:
    """Only the fields read/written by the extracted production methods."""

    def __init__(self, *, mode="mix", delta=0.05, profile=None, voltage_v=14.4):
        self.request = SimpleNamespace(
            operation_mode=mode,
            stop=SimpleNamespace(delta=delta),
            profile=profile,
            voltage_v=voltage_v,
        )
        self.started_at = 0.0
        self._imin = None
        self._vmax = None
        self._delta_confirmations = 0
        self._last_delta_confirmation = 0.0
        self.finish_hold_started_at = None
        self.main_tail_current_threshold_a = _METHODS["MANUAL_DEFAULT_MAIN_TAIL_CURRENT_A"]
        self.phase_lifecycle = SimpleNamespace(
            confirmations=0, hold_started_at=None, evaluate_main=lambda **kwargs: None,
        )
        self.main_min_confirmations = 0
        self.main_min_hold_started_at = None

    def _delta_reason(self, sample, *, now):
        return _METHODS["_delta_reason"](self, sample, now=now)

    def _main_tail_reason(self, live):
        return evaluate_manual_main_tail(self, live)

    def _mix_hold_reason(self, *, now):
        return evaluate_manual_mix_hold(self, now=now)


def sample(mode, voltage=15.0, current=1.0):
    return ManualDeltaSample(
        mode=mode.lower(),
        voltage_v=voltage,
        current_a=current,
    )


def live_sample(mode, voltage=15.0, current=1.0):
    return {
        "regulation_code": 0 if mode == "CV" else 1,
        "battery_voltage": voltage,
        "current": current,
    }


class ManualDeltaContractTests(unittest.TestCase):
    def test_cv_first_current_sets_minimum_then_confirmed_rise_counts(self):
        state = ManualEvidenceState()
        self.assertIsNone(state._delta_reason(sample("CV", current=1.0), now=120.0))
        self.assertEqual(state._imin, 1.0)
        self.assertEqual((state._delta_confirmations, state._last_delta_confirmation), (0, 0.0))
        for now in (180.0, 240.0):
            self.assertIsNone(state._delta_reason(sample("CV", current=1.05), now=now))
        self.assertEqual((state._delta_confirmations, state._last_delta_confirmation), (2, 240.0))
        self.assertEqual(state._delta_reason(sample("CV", current=1.05), now=300.0), "manual_delta_confirmed")

    def test_cc_first_voltage_sets_maximum_then_confirmed_fall_counts(self):
        state = ManualEvidenceState()
        self.assertIsNone(state._delta_reason(sample("CC", voltage=15.0), now=120.0))
        self.assertEqual(state._vmax, 15.0)
        for now in (180.0, 240.0):
            self.assertIsNone(state._delta_reason(sample("CC", voltage=14.95), now=now))
        self.assertEqual(state._delta_reason(sample("CC", voltage=14.95), now=300.0), "manual_delta_confirmed")

    def test_blank_window_is_120_seconds_inclusive_at_boundary(self):
        state = ManualEvidenceState()
        state.started_at = 10.0
        self.assertIsNone(state._delta_reason(sample("CV"), now=129.999))
        self.assertIsNone(state._imin)
        self.assertIsNone(state._delta_reason(sample("CV"), now=130.0))
        self.assertEqual(state._imin, 1.0)

    def test_confirmation_window_requires_three_spaced_samples_without_profile(self):
        state = ManualEvidenceState()
        state._delta_reason(sample("CV", current=1.0), now=120.0)
        self.assertIsNone(state._delta_reason(sample("CV", current=1.05), now=180.0))
        self.assertIsNone(state._delta_reason(sample("CV", current=1.05), now=239.999))
        self.assertEqual(state._delta_confirmations, 1)
        self.assertIsNone(state._delta_reason(sample("CV", current=1.05), now=240.0))
        self.assertEqual(state._delta_reason(sample("CV", current=1.05), now=300.0), "manual_delta_confirmed")

    def test_equal_and_backward_provided_times_do_not_add_confirmations(self):
        state = ManualEvidenceState()
        state._delta_reason(sample("CV", current=1.0), now=120.0)
        self.assertIsNone(state._delta_reason(sample("CV", current=1.05), now=180.0))
        self.assertEqual((state._delta_confirmations, state._last_delta_confirmation), (1, 180.0))
        for now in (180.0, 170.0):
            with self.subTest(now=now):
                self.assertIsNone(state._delta_reason(sample("CV", current=1.05), now=now))
                self.assertEqual((state._delta_confirmations, state._last_delta_confirmation), (1, 180.0))
        self.assertIsNone(state._delta_reason(sample("CV", current=1.05), now=240.0))
        self.assertEqual((state._delta_confirmations, state._last_delta_confirmation), (2, 240.0))
        self.assertEqual(state._delta_reason(sample("CV", current=1.05), now=300.0), "manual_delta_confirmed")

    def test_unknown_regulation_resets_delta_confirmation_without_rewriting_reference(self):
        state = ManualEvidenceState()
        state._delta_reason(sample("CV", current=1.0), now=120.0)
        state._delta_reason(sample("CV", current=1.05), now=180.0)
        self.assertEqual(state._delta_confirmations, 1)
        self.assertIsNone(state._delta_reason(
            sample("UNKNOWN", voltage=15.0, current=1.05), now=240.0
        ))
        self.assertEqual((state._imin, state._delta_confirmations), (1.0, 0))

    def test_profile_overrides_threshold_count_and_interval(self):
        profile = SimpleNamespace(mix=SimpleNamespace(
            delta_current_a=0.20, delta_voltage_v=0.40,
            confirmation_count=2, confirmation_interval_seconds=10.0, hold_hours=0.5,
        ))
        state = ManualEvidenceState(profile=profile, delta=0.01)
        state._delta_reason(sample("CV", current=1.0), now=120.0)
        self.assertIsNone(state._delta_reason(sample("CV", current=1.10), now=130.0))
        self.assertEqual(state._delta_confirmations, 0)
        self.assertIsNone(state._delta_reason(sample("CV", current=1.20), now=140.0))
        self.assertEqual(state._delta_confirmations, 1)
        self.assertEqual(state._delta_reason(sample("CV", current=1.20), now=150.0), "manual_delta_confirmed")

    def test_missing_measurement_and_unknown_mode_do_not_trigger(self):
        state = ManualEvidenceState()
        for normalized_sample in (
            ManualDeltaSample(mode="cv", voltage_v=None, current_a=1.0),
            ManualDeltaSample(mode="cv", voltage_v=15.0, current_a=None),
            ManualDeltaSample(mode="unknown", voltage_v=15.0, current_a=1.0),
        ):
            self.assertIsNone(state._delta_reason(normalized_sample, now=120.0))
        self.assertEqual((state._imin, state._vmax, state._delta_confirmations), (None, None, 0))

    def test_changed_minimum_or_maximum_resets_confirmation_evidence(self):
        cv = ManualEvidenceState()
        cv._delta_reason(sample("CV", current=1.0), now=120.0)
        cv._delta_reason(sample("CV", current=1.05), now=180.0)
        self.assertEqual(cv._delta_confirmations, 1)
        self.assertIsNone(cv._delta_reason(sample("CV", current=0.9), now=181.0))
        self.assertEqual((cv._imin, cv._delta_confirmations, cv._last_delta_confirmation), (0.9, 0, 0.0))
        cc = ManualEvidenceState()
        cc._delta_reason(sample("CC", voltage=15.0), now=120.0)
        cc._delta_reason(sample("CC", voltage=14.95), now=180.0)
        self.assertEqual(cc._delta_confirmations, 1)
        self.assertIsNone(cc._delta_reason(sample("CC", voltage=15.2), now=181.0))
        self.assertEqual((cc._vmax, cc._delta_confirmations, cc._last_delta_confirmation), (15.2, 0, 0.0))

    def test_main_tail_requires_cv_target_voltage_and_current_rule(self):
        state = ManualEvidenceState(mode="main", voltage_v=14.4)
        self.assertIsNone(state._main_tail_reason(live_sample("CV", voltage=14.19, current=0.2)))
        self.assertIsNone(state._main_tail_reason({"regulation_code": 0, "current": 0.2}))
        self.assertIsNone(state._main_tail_reason(live_sample("CC", voltage=14.4, current=0.2)))
        state._imin = 1.0
        self.assertIsNone(state._main_tail_reason(live_sample("CV", voltage=14.21, current=0.31)))
        self.assertEqual(state._main_tail_reason(live_sample("CV", voltage=14.21, current=0.30)), "manual_main_cv_imin")

    def test_profile_main_tail_evidence_delegates_to_lifecycle(self):
        calls = []
        profile = SimpleNamespace(mix=SimpleNamespace(hold_hours=1.0))
        state = ManualEvidenceState(mode="main", profile=profile)
        state.phase_lifecycle = SimpleNamespace(
            confirmations=2, hold_started_at=50.0,
            evaluate_main=lambda **kwargs: calls.append(kwargs) or "accepted",
        )
        self.assertEqual(state._main_tail_reason(live_sample("CV", voltage=14.4)), "manual_main_to_mix")
        self.assertEqual(state.main_min_confirmations, 2)
        self.assertEqual(state.main_min_hold_started_at, 50.0)
        self.assertEqual(calls[0]["profile"], profile)

    def test_mix_hold_uses_configured_profile_or_default_duration(self):
        default = ManualEvidenceState()
        default.finish_hold_started_at = 100.0
        self.assertIsNone(default._mix_hold_reason(now=100.0 + MANUAL_MIX_FINISH_HOLD_SEC - 0.001))
        self.assertEqual(default._mix_hold_reason(now=100.0 + MANUAL_MIX_FINISH_HOLD_SEC), "manual_mix_delta_hold_complete")
        profile = SimpleNamespace(mix=SimpleNamespace(hold_hours=0.5))
        configured = ManualEvidenceState(profile=profile)
        configured.finish_hold_started_at = 100.0
        self.assertIsNone(configured._mix_hold_reason(now=1899.999))
        self.assertEqual(configured._mix_hold_reason(now=1900.0), "manual_mix_delta_hold_complete")

    def test_mix_hold_completion_keeps_reason_and_emits_one_existing_log(self):
        state = ManualEvidenceState()
        state.finish_hold_started_at = 1.0
        with self.assertLogs("rd6018.manual", level="INFO") as captured:
            reason = state._mix_hold_reason(now=7201.0)
        self.assertEqual(reason, "manual_mix_delta_hold_complete")
        self.assertEqual(len(captured.records), 1)
        self.assertIn("hold_hours=2.00 timestamp=7201.000", captured.records[0].getMessage())

    def test_strategy_hold_predicate_boundaries_modes_anchor_and_durations(self):
        self.assertFalse(manual_mix_finish_hold_complete(
            operation_mode="main", hold_started_at=0.0,
            configured_hold_hours=None, now=7200.0,
        ))
        self.assertFalse(manual_mix_finish_hold_complete(
            operation_mode="mix", hold_started_at=None,
            configured_hold_hours=None, now=7200.0,
        ))
        for now, expected in ((7199.999, False), (7200.0, True), (7200.001, True)):
            with self.subTest(now=now):
                self.assertEqual(manual_mix_finish_hold_complete(
                    operation_mode="mix", hold_started_at=0.0,
                    configured_hold_hours=None, now=now,
                ), expected)
        self.assertFalse(manual_mix_finish_hold_complete(
            operation_mode="mix", hold_started_at=100.0,
            configured_hold_hours=0.5, now=1899.999,
        ))
        self.assertTrue(manual_mix_finish_hold_complete(
            operation_mode="mix", hold_started_at=100.0,
            configured_hold_hours=0.5, now=1900.0,
        ))


if __name__ == "__main__":
    unittest.main()
