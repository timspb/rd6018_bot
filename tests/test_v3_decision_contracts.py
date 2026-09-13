import ast
import pathlib
import unittest

from runtime.charge import (
    ChargeDecisionCase,
    ChargeIntent,
    DecisionValidationResult,
    DecisionValidationStatus,
    ManualProgram,
    ManualTargets,
    MinimumConfig,
    MinimumProgram,
    validate_case,
)
from runtime.charge.contracts import manual_cases, minimum_cases


class V3DecisionContractTests(unittest.TestCase):
    def test_representative_cases_load(self):
        self.assertEqual(("manual-basic",), tuple(case.case_id for case in manual_cases))
        self.assertEqual(("minimum-active", "minimum-complete"), tuple(case.case_id for case in minimum_cases))
        self.assertTrue(all(isinstance(case, ChargeDecisionCase) for case in manual_cases + minimum_cases))

    def test_manual_and_minimum_vectors_match_native_programs(self):
        manual_case = manual_cases[0]
        manual_result = validate_case(
            manual_case,
            ManualProgram(manual_case.battery_profile, ManualTargets(14.7, 5.0, "manual", "MANUAL_START")),
        )
        self.assertIs(DecisionValidationStatus.MATCH, manual_result.status)

        for case in minimum_cases:
            result = validate_case(
                case,
                MinimumProgram(case.battery_profile, MinimumConfig(**case.input_config)),
            )
            self.assertIs(DecisionValidationStatus.MATCH, result.status)

    def test_mismatch_has_field_expected_actual_and_reason(self):
        case = manual_cases[0]
        actual = ChargeIntent(14.6, 5.0, "manual", False, "MANUAL_START")

        result = DecisionValidationResult.compare(case, actual)

        self.assertIs(DecisionValidationStatus.MISMATCH, result.status)
        self.assertEqual(1, len(result.mismatches))
        self.assertEqual("target_voltage", result.mismatches[0].field)
        self.assertEqual(14.7, result.mismatches[0].expected)
        self.assertEqual(14.6, result.mismatches[0].actual)
        self.assertTrue(result.mismatches[0].reason)

    def test_contracts_have_no_external_or_actuator_imports(self):
        root = pathlib.Path(__file__).parents[1] / "runtime" / "charge" / "contracts"
        forbidden = {"bot_legacy", "hass_api", "aiogram", "rd_control_mode", "safe_output", "turn_on", "turn_off"}
        for path in root.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertTrue(forbidden.isdisjoint(text.split()), path.name)
            tree = ast.parse(text, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or "").split(".")[0], forbidden)


if __name__ == "__main__":
    unittest.main()
