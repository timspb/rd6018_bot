"""Parity and ownership checks for extracted Manual phase evidence."""

import ast
import subprocess
import unittest
from pathlib import Path

from application.manual_phase_evidence import (
    evaluate_manual_main_tail,
    evaluate_manual_mix_hold,
)
from manual_mode import MANUAL_DEFAULT_MAIN_TAIL_CURRENT_A
from runtime.charge.evidence.first_stage_variables import (
    MANUAL_DEFAULT_MAIN_TAIL_CURRENT_A as MANUAL_DEFAULT_MAIN_TAIL_CURRENT_SPEC,
    NEAR_TARGET_MARGIN_V,
)
from runtime.charge.programs.manual import manual_main_tail_reached


ROOT = Path(__file__).resolve().parents[1]


def _function_body(source: str, owner: str, function: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == owner)
    return next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == function)


def _without_session_alias(function: ast.FunctionDef) -> list[ast.stmt]:
    body = list(function.body)
    alias = ast.Assign(
        targets=[ast.Name(id="self", ctx=ast.Store())],
        value=ast.Name(id="session", ctx=ast.Load()),
    )
    if body and ast.dump(body[0], include_attributes=False) == ast.dump(alias, include_attributes=False):
        body.pop(0)
    return body


class ManualPhaseEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.head_source = subprocess.run(
            ["git", "show", "3c692554074b27805419a9b0767133a1c8d78150:manual_mode.py"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout
        cls.current_source = (ROOT / "manual_mode.py").read_text(encoding="utf-8")
        cls.evidence_source = (ROOT / "application/manual_phase_evidence.py").read_text(encoding="utf-8")

    def test_extracted_bodies_match_original_head_after_session_alias(self):
        for method_name, extracted in (
            ("_main_tail_reason", evaluate_manual_main_tail),
        ):
            with self.subTest(method=method_name):
                original = _function_body(self.head_source, "ManualSessionManager", method_name)
                moved = ast.parse(self.evidence_source)
                moved_function = next(node for node in moved.body if isinstance(node, ast.FunctionDef) and node.name == extracted.__name__)

                class ApprovedOwnerRelocations(ast.NodeTransformer):
                    def visit_Compare(self, node):
                        node = self.generic_visit(node)
                        if ast.unparse(node) == "voltage < float(self.request.voltage_v) - 0.2":
                            return ast.parse(
                                "voltage < float(self.request.voltage_v) - float(NEAR_TARGET_MARGIN_V.default)",
                                mode="eval",
                            ).body
                        return node

                    def visit_If(self, node):
                        node = self.generic_visit(node)
                        if ast.unparse(node.test) == "self._imin is None or current <= self.main_tail_current_threshold_a":
                            node.test = ast.parse(
                                "manual_main_tail_reached(imin=self._imin, current_a=current, threshold_a=self.main_tail_current_threshold_a)",
                                mode="eval",
                            ).body
                        return node

                normalized_original = ApprovedOwnerRelocations().visit(
                    ast.fix_missing_locations(ast.Module(body=original.body, type_ignores=[]))
                )
                self.assertEqual(
                    ast.dump(normalized_original, include_attributes=False),
                    ast.dump(
                        ast.Module(body=_without_session_alias(moved_function), type_ignores=[]),
                        include_attributes=False,
                    ),
                )

    def test_profileless_main_tail_policy_is_owned_by_manual_program(self):
        self.assertTrue(manual_main_tail_reached(imin=None, current_a=1.2, threshold_a=0.30))
        self.assertTrue(manual_main_tail_reached(imin=0.40, current_a=0.30, threshold_a=0.30))
        self.assertFalse(manual_main_tail_reached(imin=0.40, current_a=0.31, threshold_a=0.30))

        evidence_tree = ast.parse(self.evidence_source)
        imported = [
            (node.module, alias.name)
            for node in ast.walk(evidence_tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        ]
        self.assertIn(("runtime.charge.programs.manual", "manual_main_tail_reached"), imported)
        self.assertNotIn("self._imin is None or current <= self.main_tail_current_threshold_a", self.evidence_source)

    def test_fallback_tail_threshold_has_one_typed_first_stage_owner(self):
        self.assertEqual(MANUAL_DEFAULT_MAIN_TAIL_CURRENT_SPEC.default, 0.30)
        self.assertEqual(MANUAL_DEFAULT_MAIN_TAIL_CURRENT_SPEC.unit, "A")
        self.assertEqual(
            MANUAL_DEFAULT_MAIN_TAIL_CURRENT_SPEC.key,
            "charge.evidence.first_stage.manual_default_main_tail_current_a",
        )
        self.assertEqual(MANUAL_DEFAULT_MAIN_TAIL_CURRENT_SPEC.owner, "runtime.charge.evidence.first_stage")
        self.assertEqual(MANUAL_DEFAULT_MAIN_TAIL_CURRENT_A, float(MANUAL_DEFAULT_MAIN_TAIL_CURRENT_SPEC.default))

    def test_manual_near_target_margin_uses_the_existing_first_stage_variable(self):
        self.assertEqual(NEAR_TARGET_MARGIN_V.default, 0.20)
        strategy_source = (
            ROOT / "runtime/charge/strategy/manual_phase_lifecycle.py"
        ).read_text(encoding="utf-8")
        self.assertIn("NEAR_TARGET_MARGIN_V.default", strategy_source)
        self.assertIn("NEAR_TARGET_MARGIN_V.default", self.evidence_source)
        self.assertNotIn(" - 0.20", strategy_source)
        self.assertNotIn(" - 0.20", self.evidence_source)

    def test_mix_hold_delegates_to_strategy_and_preserves_reason(self):
        state = type("Session", (), {})()
        state.request = type("Request", (), {"operation_mode": "mix", "profile": None})()
        state.finish_hold_started_at = 10.0
        self.assertEqual(
            evaluate_manual_mix_hold(state, now=10.0 + 7200),
            "manual_mix_delta_hold_complete",
        )
        evidence_tree = ast.parse(self.evidence_source)
        imported = [
            node.module for node in ast.walk(evidence_tree)
            if isinstance(node, ast.ImportFrom)
        ]
        self.assertNotIn("application.manual_observer_use_case", imported)
        self.assertIn("runtime.charge.strategy.manual_phase_lifecycle", imported)

    def test_session_methods_are_thin_delegates(self):
        for name, expected_call in (
            ("_main_tail_reason", "evaluate_manual_main_tail"),
            ("_mix_hold_reason", "evaluate_manual_mix_hold"),
        ):
            with self.subTest(method=name):
                method = _function_body(self.current_source, "ManualSessionManager", name)
                self.assertEqual(len(method.body), 1)
                returned = method.body[0]
                self.assertIsInstance(returned, ast.Return)
                call = returned.value
                self.assertIsInstance(call, ast.Call)
                self.assertIsInstance(call.func, ast.Name)
                self.assertEqual(call.func.id, expected_call)

    def test_evidence_module_has_no_monolith_or_production_runtime_import(self):
        tree = ast.parse(self.evidence_source)
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        self.assertFalse(any(name in {"manual_mode", "runtime.production_runtime"} for name in imports))


if __name__ == "__main__":
    unittest.main()
