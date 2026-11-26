"""Pure contract tests for adopted MIX source eligibility and sample projection."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from unittest.mock import patch

from rd6018_telemetry import RegulationMode
from runtime.safety.runtime_guard import RuntimeSafetyError
from runtime.charge.evidence.adopted_mix_sample_decision import (
    classify_adopted_mix_source_timestamp,
    project_adopted_mix_signal_sample,
)
from signal_analyzer import SignalSample


class AdoptedMixSampleDecisionTests(unittest.TestCase):
    def test_missing_timestamp_raises_exact_error(self):
        with self.assertRaisesRegex(
            RuntimeSafetyError, "^MIX_ADOPTED source timestamps unavailable$"
        ):
            classify_adopted_mix_source_timestamp(None, 10.0)

    def test_stale_and_equal_timestamp_are_ineligible(self):
        self.assertFalse(classify_adopted_mix_source_timestamp(10.0, 10.0))
        self.assertFalse(classify_adopted_mix_source_timestamp(9.0, 10.0))

    def test_newer_timestamp_is_eligible_without_prior_timestamp(self):
        self.assertTrue(classify_adopted_mix_source_timestamp(10.0, None))

    def test_cv_and_cc_project_exact_signal_samples(self):
        cases = (
            (RegulationMode.CV, True, False),
            (RegulationMode.CC, False, True),
        )
        for mode, is_cv, is_cc in cases:
            with self.subTest(mode=mode):
                sample = project_adopted_mix_signal_sample(12.5, 16.4, 0.9, 24.0, mode)
                self.assertEqual(
                    sample,
                    SignalSample(12.5, 16.4, 0.9, 24.0, is_cv=is_cv, is_cc=is_cc),
                )

    def test_missing_or_invalid_coherent_values_raise_exact_error(self):
        invalid_cases = (
            (None, 1.0, 20.0, RegulationMode.CV),
            (16.0, None, 20.0, RegulationMode.CV),
            (16.0, 1.0, None, RegulationMode.CV),
            (16.0, 1.0, 20.0, None),
            (16.0, 1.0, 20.0, "UNKNOWN"),
        )
        for values in invalid_cases:
            with self.subTest(values=values), self.assertRaisesRegex(
                RuntimeSafetyError,
                "^MIX_ADOPTED coherent U/I/T/CV-CC sample unavailable$",
            ):
                project_adopted_mix_signal_sample(12.5, *values)

    def test_module_imports_only_declared_domain_types_and_safety_error(self):
        path = Path("runtime/charge/evidence/adopted_mix_sample_decision.py")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        self.assertEqual(
            imports,
            {
                "__future__",
                "rd6018_telemetry",
                "runtime.safety.runtime_guard",
                "signal_analyzer",
            },
        )
        self.assertFalse(any(isinstance(node, ast.Import) for node in ast.walk(tree)))


if __name__ == "__main__":
    unittest.main()
