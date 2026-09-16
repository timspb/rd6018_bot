"""Phase 8.0 application orchestration tests; no infrastructure integration."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
import unittest

from application.charge_orchestration import ChargeApplicationService, TelemetrySnapshot
from application.intents import OperatorIntent, OperatorIntentKind
from runtime.charge import ProfileRegistry, SessionManager, SessionStatus


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "application" / "charge_orchestration.py"


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            values.append(node.module or "")
    return values


class ApplicationOrchestrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ChargeApplicationService(ProfileRegistry.with_defaults(), SessionManager())
        self.telemetry = TelemetrySnapshot(14.2, 2.0, 23.0, False, datetime.now(timezone.utc))

    def test_start_flow_returns_domain_decision_without_execution(self) -> None:
        intent = OperatorIntent(OperatorIntentKind.START_CHARGE, "test", "operator", {"profile": "AGM", "capacity_ah": 70, "session_id": "s1"})
        result = self.service.handle(intent, self.telemetry)
        self.assertTrue(result.accepted)
        self.assertEqual(SessionStatus.ACTIVE, result.session.status)
        self.assertIsNotNone(result.domain)
        self.assertIsNotNone(result.domain.intent)

    def test_telemetry_update_flow(self) -> None:
        start = OperatorIntent(OperatorIntentKind.START_CHARGE, "test", "operator", {"profile": "EFB", "capacity_ah": 70})
        self.service.handle(start, self.telemetry)
        result = self.service.handle(OperatorIntent(OperatorIntentKind.REFRESH_PANEL, "test", "operator"), self.telemetry)
        self.assertTrue(result.accepted)
        self.assertEqual("domain_evaluated", result.reason)

    def test_stop_flow_returns_containment_request_only(self) -> None:
        start = OperatorIntent(OperatorIntentKind.START_CHARGE, "test", "operator", {"profile": "CA_CA", "capacity_ah": 70})
        self.service.handle(start, self.telemetry)
        result = self.service.handle(OperatorIntent(OperatorIntentKind.STOP_CHARGE, "test", "operator"), self.telemetry)
        self.assertTrue(result.accepted)
        self.assertEqual(SessionStatus.STOPPED, result.session.status)
        self.assertEqual("operator_stop", result.domain.containment.trigger)

    def test_invalid_start_has_no_session_side_effect(self) -> None:
        result = self.service.handle(OperatorIntent(OperatorIntentKind.START_CHARGE, "test", "operator", {}), self.telemetry)
        self.assertFalse(result.accepted)
        self.assertEqual(SessionStatus.IDLE, result.session.status)

    def test_service_has_no_infrastructure_or_physical_imports(self) -> None:
        forbidden = ("hass_api", "homeassistant", "esphome", "rd_transport", "runtime.physical", "runtime.output", "telegram", "database", "persistence")
        violations = [name for name in _imports(SERVICE) if any(token in name.lower() for token in forbidden)]
        self.assertEqual([], violations)
        source = SERVICE.read_text(encoding="utf-8")
        for token in ("turn_on(", "turn_off(", "set_voltage(", "set_current(", "get_all_live("):
            self.assertNotIn(token, source)

    def test_document_tracks_application_boundary(self) -> None:
        text = (ROOT / "docs" / "RD6018_APPLICATION_ORCHESTRATION_MODEL.md").read_text(encoding="utf-8")
        for term in ("ChargeApplicationService", "OperatorIntent", "TelemetrySnapshot", "ApplicationDecision", "does not execute"):
            self.assertIn(term, text)


if __name__ == "__main__":
    unittest.main()
