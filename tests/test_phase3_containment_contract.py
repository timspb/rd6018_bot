"""Read-only tests for the Phase 3 containment result contract."""

from __future__ import annotations

import ast
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from application.containment_result import (
    ContainmentResult,
    ContainmentVerificationState,
)


ROOT = Path(__file__).resolve().parents[1]


class Phase3ContainmentContractTests(unittest.TestCase):
    def make_result(self) -> ContainmentResult:
        return ContainmentResult.new(
            trace_id="trace-1",
            source="runtime_watchdog",
            trigger="telemetry_timeout",
            requested_action="verified_output_off",
            physical_owner="v2_safety_output",
            verification_state=ContainmentVerificationState.REQUESTED,
        )

    def test_contract_is_immutable(self):
        result = self.make_result()
        with self.assertRaises(FrozenInstanceError):
            result.source = "other"  # type: ignore[misc]

    def test_schema_and_enum_validation(self):
        result = self.make_result()
        self.assertEqual(result.verification_state, ContainmentVerificationState.REQUESTED)
        self.assertEqual(result.to_dict()["verification_state"], "requested")
        with self.assertRaises(ValueError):
            ContainmentResult(
                event_id="",
                trace_id="trace",
                source="source",
                trigger="trigger",
                requested_action="off",
                physical_owner="owner",
                verification_state="invalid",  # type: ignore[arg-type]
            )

    def test_all_verification_states_are_present(self):
        self.assertEqual(
            {state.value for state in ContainmentVerificationState},
            {
                "not_requested",
                "requested",
                "off_confirmed",
                "off_unconfirmed",
                "failed",
                "unknown",
            },
        )

    def test_contract_has_no_physical_runtime_imports_or_calls(self):
        path = ROOT / "application" / "containment_result.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        self.assertTrue(all(not name.startswith("runtime.physical") for name in imports))
        self.assertNotIn("hass_api", imports)
        self.assertNotIn("safe_output", imports)
        calls = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertTrue(calls.isdisjoint({"turn_on", "turn_off", "set_voltage", "set_current"}))

    def test_ownership_document_exists(self):
        self.assertTrue((ROOT / "docs" / "RD6018_CONTAINMENT_OWNERSHIP_MODEL.md").is_file())


if __name__ == "__main__":
    unittest.main()
