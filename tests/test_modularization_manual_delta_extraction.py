"""Owner-boundary and purity contracts for the Manual Delta evidence transform."""

import ast
import unittest
from pathlib import Path

from runtime.charge.evidence.manual_delta import (
    ManualDeltaEvidencePolicy,
    ManualDeltaEvidenceState,
    ManualDeltaSample,
    evaluate_manual_delta_evidence,
)


ROOT = Path(__file__).resolve().parents[1]


def _method(tree, class_name, method_name):
    owner = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return next(
        node for node in owner.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )


def _function(tree, function_name):
    return next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )


class ManualDeltaExtractionTests(unittest.TestCase):
    def test_evaluator_has_explicit_state_policy_sample_api_and_no_session_dependency(self):
        path = ROOT / "runtime/charge/evidence/manual_delta.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        function = _function(tree, "evaluate_manual_delta_evidence")
        arguments = [argument.arg for argument in function.args.args]
        self.assertEqual(arguments, ["state", "policy", "sample"])
        self.assertEqual(
            [argument.arg for argument in function.args.kwonlyargs],
            ["started_at", "now"],
        )
        imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        self.assertNotIn("rd6018_telemetry", imports)
        self.assertNotIn("manual_mode", imports)
        self.assertFalse(any(module and module.startswith("application") for module in imports))
        self.assertNotIn("session", arguments)
        self.assertNotIn("request", arguments)

    def test_manager_is_the_only_adapter_that_projects_evidence_state(self):
        tree = ast.parse((ROOT / "manual_mode.py").read_text(encoding="utf-8"))
        method = _method(tree, "ManualSessionManager", "_delta_reason")
        source = ast.unparse(method)
        for expected in (
            "ManualDeltaEvidenceState",
            "ManualDeltaEvidencePolicy",
            "evaluate_manual_delta_evidence",
            "self._imin = result.state.imin",
            "self._vmax = result.state.vmax",
            "self._delta_confirmations = result.state.confirmations",
            "self._last_delta_confirmation = result.state.last_confirmation_at",
        ):
            self.assertIn(expected, source)
        self.assertNotIn("evaluate_manual_delta_evidence(self", source)

    def test_application_normalizes_sample_before_calling_session_adapter(self):
        tree = ast.parse(
            (ROOT / "application/manual_observer_use_case.py").read_text(encoding="utf-8")
        )
        source = ast.unparse(tree)
        self.assertIn("ManualDeltaSample", source)
        self.assertIn("mode=resolve_regulation(live).value", source)
        self.assertIn("voltage_v=voltage", source)
        self.assertIn("current_a=current", source)
        self.assertIn("self._delta_reason(delta_sample, now=now)", source)
        self.assertNotIn("self._delta_reason(live, now=now)", source)

    def test_evaluator_returns_new_state_without_mutating_input_and_preserves_sequence(self):
        initial = ManualDeltaEvidenceState()
        policy = ManualDeltaEvidencePolicy(
            delta_current_a=0.05,
            delta_voltage_v=0.05,
        )
        first = evaluate_manual_delta_evidence(
            initial,
            policy,
            ManualDeltaSample(mode="cv", voltage_v=15.0, current_a=1.0),
            started_at=0.0,
            now=120.0,
        )
        self.assertEqual(initial, ManualDeltaEvidenceState())
        self.assertIsNot(first.state, initial)
        self.assertEqual(first.state.imin, 1.0)
        self.assertEqual(first.state.confirmations, 0)

        state = first.state
        for now in (180.0, 240.0):
            result = evaluate_manual_delta_evidence(
                state,
                policy,
                ManualDeltaSample(mode="cv", voltage_v=15.0, current_a=1.05),
                started_at=0.0,
                now=now,
            )
            state = result.state
            self.assertIsNone(result.reason)
        final = evaluate_manual_delta_evidence(
            state,
            policy,
            ManualDeltaSample(mode="cv", voltage_v=15.0, current_a=1.05),
            started_at=0.0,
            now=300.0,
        )
        self.assertEqual(final.reason, "manual_delta_confirmed")
        self.assertEqual(final.state.confirmations, 3)

    def test_missing_sample_preserves_state_object(self):
        state = ManualDeltaEvidenceState(
            imin=0.8,
            vmax=15.1,
            confirmations=2,
            last_confirmation_at=180.0,
        )
        result = evaluate_manual_delta_evidence(
            state,
            ManualDeltaEvidencePolicy(delta_current_a=0.05, delta_voltage_v=0.05),
            ManualDeltaSample(mode="cv", voltage_v=None, current_a=1.0),
            started_at=0.0,
            now=240.0,
        )
        self.assertIs(result.state, state)
        self.assertEqual(result.state.confirmations, 2)


if __name__ == "__main__":
    unittest.main()
