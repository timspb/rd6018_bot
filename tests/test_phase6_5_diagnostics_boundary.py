"""Phase 6.5 diagnostics contracts; no runtime wiring or side effects."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

from application.diagnostics_domain import (
    DiagnosticCategory,
    DiagnosticEvent,
    DiagnosticSeverity,
    DiagnosticsDomain,
    TraceCorrelation,
)


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "application" / "diagnostics_domain.py"


class DiagnosticsBoundaryTests(unittest.TestCase):
    def test_immutable_event_and_correlation(self) -> None:
        correlation = TraceCorrelation("trace-1", "span-1", session_id="session-1")
        event = DiagnosticEvent.new(
            category=DiagnosticCategory.DOMAIN,
            event_type="phase_changed",
            severity=DiagnosticSeverity.INFO,
            correlation=correlation,
            source="charge-domain",
            payload={"phase": "MAIN", "nested": {"value": 1}},
        )
        with self.assertRaises(TypeError):
            event.payload["new"] = True  # type: ignore[index]
        self.assertEqual("trace-1", event.to_dict()["correlation"]["trace_id"])
        self.assertEqual("MAIN", event.to_dict()["payload"]["phase"])

    def test_domain_infrastructure_and_operator_categories(self) -> None:
        domain = DiagnosticsDomain()
        correlation = TraceCorrelation("trace-1", "span-1")
        for category, event_type in (
            (DiagnosticCategory.DOMAIN, "strategy_decision"),
            (DiagnosticCategory.INFRASTRUCTURE, "ha_unavailable"),
            (DiagnosticCategory.OPERATOR, "diagnostic_requested"),
        ):
            event = domain.event(
                category=category,
                event_type=event_type,
                severity=DiagnosticSeverity.INFO,
                correlation=correlation,
                source="test",
            )
            self.assertEqual(category, event.category)

    def test_error_warning_and_audit_fields_are_transport_independent(self) -> None:
        event = DiagnosticEvent.new(
            category=DiagnosticCategory.INFRASTRUCTURE,
            event_type="transport_timeout",
            severity=DiagnosticSeverity.ERROR,
            correlation=TraceCorrelation("trace-2", "span-2"),
            source="transport",
            error_code="TIMEOUT",
            warning_code="DEGRADED",
            audit_action="observed",
        )
        payload = event.to_dict()
        self.assertEqual("TIMEOUT", payload["error_code"])
        self.assertEqual("DEGRADED", payload["warning_code"])
        self.assertEqual("observed", payload["audit_action"])

    def test_diagnostics_module_has_no_forbidden_imports_or_calls(self) -> None:
        tree = ast.parse(MODULE.read_text(encoding="utf-8"), filename=str(MODULE))
        forbidden = ("telegram", "hass", "esphome", "physical", "controller", "safety", "sqlite", "yaml")
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append((node.module or "").lower())
        self.assertEqual([], [name for name in imports if any(item in name for item in forbidden)])
        text = MODULE.read_text(encoding="utf-8").lower()
        self.assertNotIn("controller.start", text)
        self.assertNotIn("controller.stop", text)
        self.assertNotIn("output_on", text)
        self.assertNotIn("output_off", text)

    def test_boundary_document_declares_ownership_and_forbidden_side_effects(self) -> None:
        text = (ROOT / "docs" / "RD6018_DIAGNOSTICS_BOUNDARY_MODEL.md").read_text(encoding="utf-8")
        for phrase in ("Domain", "Infrastructure", "Operator", "TraceCorrelation", "DiagnosticEvent", "physical execution"):
            self.assertIn(phrase, text)
        self.assertIn("не импортирует и не вызывает", text)


if __name__ == "__main__":
    unittest.main()
