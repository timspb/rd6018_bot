import ast
from pathlib import Path
import unittest

from runtime.charge.evidence.first_stage import (
    FirstStageState,
    MainSampleEvidenceEvaluator,
    MainSampleEvidenceInput,
)
from signal_analyzer import SignalAnalyzer, SignalEvent, SignalSample


class MainSampleEvidenceClockTests(unittest.TestCase):
    def sample(self, *, timestamp, profile="EFB", events=(), stage="Main Charge",
               voltage=14.8, current=1.0, is_cv=True, dtemp=0.0,
               dcurrent=-0.02, dvoltage=0.01):
        agm = profile == "AGM"
        return MainSampleEvidenceInput(
            stage=stage,
            main_stage="Main Charge",
            target_voltage_v=14.8,
            timestamp_s=timestamp,
            voltage_v=voltage,
            current_a=current,
            is_cv=is_cv,
            chemistry=profile,
            capacity_ah=100.0,
            plateau_required_minutes=120.0 if agm else 40.0,
            plateau_window_minutes=15.0,
            events=frozenset(events),
            dtemp_c_per_min=dtemp,
            dcurrent_a_per_min=dcurrent,
            dvoltage_v_per_min=dvoltage,
            temperature_c=35.0 if dtemp else 25.0,
        )

    def test_startup_and_five_samples_before_window_do_not_create_plateau(self):
        evaluator = MainSampleEvidenceEvaluator()
        self.assertIsNone(evaluator.plateau_since_s)

    def test_analyzer_five_sample_minimum_and_existing_backdating_are_preserved(self):
        analyzer = SignalAnalyzer()
        analyzer.reset_stage("main", target_voltage_v=14.8)
        result = None
        for timestamp in (50000, 50180, 50360, 50540, 50720):
            result = analyzer.observe(SignalSample(timestamp, 14.8, 1.0, 25.0, True))
        self.assertIn(SignalEvent.CURRENT_PLATEAU, result.events)
        evaluator = MainSampleEvidenceEvaluator()
        evidence = evaluator.assess(self.sample(timestamp=50720, events=result.events))
        self.assertEqual(evidence.plateau_since_s, 49820.0)
        for timestamp in (60, 180, 300, 480, 840):
            result = evaluator.assess(self.sample(timestamp=timestamp))
            self.assertIsNone(result.plateau_since_s)
        self.assertIsNone(evaluator.plateau_since_s)

    def test_plateau_clock_backdates_exactly_fifteen_minutes(self):
        evaluator = MainSampleEvidenceEvaluator()
        result = evaluator.assess(self.sample(
            timestamp=3600, events={SignalEvent.CURRENT_PLATEAU},
        ))
        self.assertEqual(result.plateau_since_s, 2700.0)
        self.assertEqual(evaluator.plateau_since_s, 2700.0)

    def test_operator_pause_shifts_the_owned_clock(self):
        evaluator = MainSampleEvidenceEvaluator()
        evaluator.plateau_since_s = 1000.0
        evaluator.shift_clock(300.0)
        self.assertEqual(evaluator.plateau_since_s, 1300.0)
        evaluator.shift_clock(-10.0)
        self.assertEqual(evaluator.plateau_since_s, 1300.0)

    def test_current_minimum_refresh_resets_clock_even_with_plateau_event(self):
        evaluator = MainSampleEvidenceEvaluator()
        evaluator.assess(self.sample(timestamp=3600, events={SignalEvent.CURRENT_PLATEAU}))
        result = evaluator.assess(self.sample(
            timestamp=3900,
            events={SignalEvent.CURRENT_PLATEAU, SignalEvent.CURRENT_MINIMUM_UPDATED},
        ))
        self.assertIsNone(result.plateau_since_s)
        self.assertIsNone(evaluator.plateau_since_s)

    def test_current_minimum_refresh_still_returns_current_tail_assessment(self):
        evaluator = MainSampleEvidenceEvaluator()
        result = evaluator.assess(self.sample(
            timestamp=3900,
            current=0.1,
            events={SignalEvent.CURRENT_MINIMUM_UPDATED, SignalEvent.CURRENT_PLATEAU},
        ))
        self.assertEqual(result.assessment.state, FirstStageState.TAIL_READY)
        self.assertIsNone(result.plateau_since_s)

    def test_plateau_event_farther_than_near_target_margin_clears_clock(self):
        evaluator = MainSampleEvidenceEvaluator()
        evaluator.assess(self.sample(timestamp=3600, events={SignalEvent.CURRENT_PLATEAU}))
        result = evaluator.assess(self.sample(
            timestamp=3900, voltage=14.59, events={SignalEvent.CURRENT_PLATEAU},
        ))
        self.assertIsNone(result.plateau_since_s)
        self.assertFalse(result.assessment.near_target)

    def test_stage_exit_and_reentry_start_a_new_clock(self):
        evaluator = MainSampleEvidenceEvaluator()
        evaluator.assess(self.sample(timestamp=3600, events={SignalEvent.CURRENT_PLATEAU}))
        exited = evaluator.assess(self.sample(timestamp=3900, stage="Mix Mode", events={SignalEvent.CURRENT_PLATEAU}))
        self.assertIsNone(exited.assessment)
        self.assertIsNone(evaluator.plateau_since_s)
        reentered = evaluator.assess(self.sample(timestamp=4200, events={SignalEvent.CURRENT_PLATEAU}))
        self.assertEqual(reentered.plateau_since_s, 3300.0)

    def test_backward_timestamp_cannot_create_positive_plateau_elapsed_time(self):
        evaluator = MainSampleEvidenceEvaluator()
        evaluator.assess(self.sample(timestamp=10000, events={SignalEvent.CURRENT_PLATEAU}))
        result = evaluator.assess(self.sample(timestamp=9000, events={SignalEvent.CURRENT_PLATEAU}))
        self.assertEqual(result.assessment.state, FirstStageState.BULK_OR_TAPER)

    def test_ca_efb_plateau_threshold_is_forty_minutes_after_backdating(self):
        evaluator = MainSampleEvidenceEvaluator()
        evaluator.assess(self.sample(timestamp=2000, events={SignalEvent.CURRENT_PLATEAU}))
        before = evaluator.assess(self.sample(timestamp=3499, events={SignalEvent.CURRENT_PLATEAU}))
        at = evaluator.assess(self.sample(timestamp=3500, events={SignalEvent.CURRENT_PLATEAU}))
        self.assertEqual(before.assessment.state, FirstStageState.BULK_OR_TAPER)
        self.assertEqual(at.assessment.state, FirstStageState.STUCK_PLATEAU)

    def test_agm_threshold_remains_one_hundred_twenty_minutes(self):
        evaluator = MainSampleEvidenceEvaluator()
        evaluator.assess(self.sample(timestamp=10000, profile="AGM", events={SignalEvent.CURRENT_PLATEAU}))
        before = evaluator.assess(self.sample(timestamp=16299, profile="AGM", events={SignalEvent.CURRENT_PLATEAU}))
        at = evaluator.assess(self.sample(timestamp=16300, profile="AGM", events={SignalEvent.CURRENT_PLATEAU}))
        self.assertEqual(before.assessment.state, FirstStageState.BULK_OR_TAPER)
        self.assertEqual(at.assessment.state, FirstStageState.STUCK_PLATEAU)

    def test_upward_thermal_and_downward_voltage_trends_remain_distinct(self):
        evaluator = MainSampleEvidenceEvaluator()
        thermal = evaluator.assess(self.sample(
            timestamp=4000, events={SignalEvent.CURRENT_PLATEAU},
            dtemp=0.13, dcurrent=0.1, dvoltage=0.01,
        ))
        self.assertEqual(thermal.assessment.state, FirstStageState.THERMALLY_UNSTABLE)
        voltage = evaluator.assess(self.sample(
            timestamp=4100, events={SignalEvent.CURRENT_PLATEAU},
            dtemp=0.0, dcurrent=-0.02, dvoltage=-0.02,
        ))
        self.assertEqual(voltage.assessment.state, FirstStageState.VOLTAGE_UNSTABLE)

    def test_restart_restore_starts_with_empty_plateau_clock(self):
        first_process = MainSampleEvidenceEvaluator()
        first_process.assess(self.sample(timestamp=3600, events={SignalEvent.CURRENT_PLATEAU}))
        restored_process = MainSampleEvidenceEvaluator()
        result = restored_process.assess(self.sample(timestamp=4000))
        self.assertIsNone(result.plateau_since_s)
        self.assertIsNone(restored_process.plateau_since_s)

    def test_controller_no_longer_owns_or_wraps_moved_mechanics(self):
        source = Path("charge_controller.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        controller = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ManagedChargeController")
        methods = {node.name for node in controller.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.assertNotIn("_update_main_plateau_clock", methods)
        self.assertNotIn("_assess_main_sample", methods)
        self.assertNotIn("_v2_main_plateau_since", source)
        self.assertIn("MainSampleEvidenceEvaluator", source)


if __name__ == "__main__":
    unittest.main()
