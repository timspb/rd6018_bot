import unittest

from battery_diagnostics import DiagnosticHypothesis, DiagnosticLevel
from battery_fault_calibration import (
    FaultCalibrationCase,
    FaultCalibrationExpectation,
    calibration_case_from_mapping,
    calibration_summary_to_mapping,
    evaluate_fault_cases,
    load_calibration_jsonl,
)
from battery_fault_engine import BatteryFaultContext, DiagnosticAuthority


class BatteryFaultCalibrationTests(unittest.TestCase):
    def test_clean_case_matches_allow(self) -> None:
        case = FaultCalibrationCase(
            case_id="healthy",
            context=BatteryFaultContext(),
            expected=FaultCalibrationExpectation(
                authority=DiagnosticAuthority.ALLOW,
                hypothesis_levels=((DiagnosticHypothesis.CELL_FAULT, DiagnosticLevel.NORMAL),),
            ),
        )
        summary = evaluate_fault_cases([case])
        self.assertEqual(summary.total_cases, 1)
        self.assertEqual(summary.authority_matches, 1)
        self.assertEqual(summary.unexpected_hv_blocks, 0)
        self.assertEqual(summary.missed_hv_blocks, 0)
        self.assertEqual(summary.hypothesis_level_mismatches, 0)

    def test_unexpected_block_is_counted_separately(self) -> None:
        case = FaultCalibrationCase(
            case_id="externally-confirmed-but-label-says-allow",
            context=BatteryFaultContext(external_failed_cell_confirmed=True),
            expected=FaultCalibrationExpectation(authority=DiagnosticAuthority.ALLOW),
        )
        summary = evaluate_fault_cases([case])
        self.assertEqual(summary.unexpected_hv_blocks, 1)
        self.assertEqual(summary.authority_matches, 0)

    def test_missed_block_is_counted(self) -> None:
        case = FaultCalibrationCase(
            case_id="labelled-block-without-current-evidence",
            context=BatteryFaultContext(),
            expected=FaultCalibrationExpectation(authority=DiagnosticAuthority.BLOCK_AUTOMATIC_HV),
        )
        summary = evaluate_fault_cases([case])
        self.assertEqual(summary.missed_hv_blocks, 1)

    def test_mapping_loader_reconstructs_nested_sg_assessment(self) -> None:
        case = calibration_case_from_mapping(
            {
                "case_id": "persistent-sg",
                "context": {
                    "specific_gravity": {
                        "valid_cell_count": 6,
                        "minimum": 1.180,
                        "maximum": 1.270,
                        "median": 1.268,
                        "spread": 0.090,
                        "low_outlier_cells": [4],
                        "high_outlier_cells": [],
                        "level": "verify",
                        "reason": "cell_specific_gravity_imbalance",
                    },
                    "sg_persisted_after_corrective_equalization": True,
                },
                "expected": {
                    "authority": "verify_before_hv",
                    "hypothesis_levels": {"stratification": "probable"},
                },
            }
        )
        self.assertEqual(case.context.specific_gravity.valid_cell_count, 6)  # type: ignore[union-attr]
        self.assertEqual(case.expected.authority, DiagnosticAuthority.VERIFY_BEFORE_HV)

    def test_jsonl_and_report_are_deterministic(self) -> None:
        cases = load_calibration_jsonl(
            '# comment\n'
            '{"case_id":"healthy","context":{},"expected":{"authority":"allow"}}\n'
            '{"case_id":"confirmed","context":{"external_failed_cell_confirmed":true},'
            '"expected":{"authority":"block_automatic_hv"}}\n'
        )
        summary = evaluate_fault_cases(cases)
        report = calibration_summary_to_mapping(summary)
        self.assertEqual(report["total_cases"], 2)
        self.assertEqual(report["authority_matches"], 2)
        self.assertEqual(report["unexpected_hv_blocks"], 0)
        self.assertEqual(report["missed_hv_blocks"], 0)


if __name__ == "__main__":
    unittest.main()
