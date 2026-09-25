"""Phase 8.6 V3 shadow composition tests."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
import unittest

from application.actuator_intent import ActuatorIntent, ActuatorOperation, ActuatorTrigger, PhysicalVerificationExpectation, RollbackPolicy, SafetyContext
from application.persistence_boundary import PersistenceKind, PersistenceRecord, StateSnapshot
from application.shadow_composition import ApplicationComposition
from application.telemetry_authority import TelemetrySource
from application.diagnostics_domain import DiagnosticCategory, DiagnosticSeverity


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "application" / "shadow_composition.py"


class ShadowCompositionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.now = datetime.now(timezone.utc).timestamp()
        self.composition = ApplicationComposition.shadow(
            config_root=ROOT,
            esp_reader=lambda: {"timestamp": self.now, "voltage": 14.1, "current": 1.2, "temperature": 23},
            ha_reader=lambda: {"timestamp": self.now, "voltage": 13.9, "current": 1.1, "temperature": 24},
        )

    def test_composition_creation_and_dependency_injection(self) -> None:
        c = self.composition
        self.assertIs(c.domain.profiles, c.application.profiles)
        self.assertIs(c.domain.sessions, c.application.sessions)
        self.assertEqual("yaml", c.configuration.value("charge.manual.main.voltage_v").source)
        self.assertIsNotNone(c.execution)
        self.assertIsNotNone(c.diagnostics)
        self.assertIsNotNone(c.persistence)

    async def test_command_telemetry_and_decision_flow(self) -> None:
        c = self.composition
        ui = c.ui.parse("START AGM 72", user="operator", trace_id="trace-composition")
        self.assertTrue(ui.accepted)
        esp = await c.telemetry.esp_direct.read()
        ha = await c.telemetry.ha.read()
        selected = c.telemetry.arbitrator.select(esp_direct=esp, ha=ha, now=datetime.fromtimestamp(self.now, timezone.utc))
        self.assertEqual(TelemetrySource.ESP_DIRECT, selected.source)
        from application.charge_orchestration import TelemetrySnapshot
        telemetry = TelemetrySnapshot(selected.voltage, selected.current, selected.temperature, selected.output_state, selected.received_at)
        decision = c.application.handle(ui.intent, telemetry)
        self.assertTrue(decision.accepted)
        self.assertIsNotNone(decision.domain)
        event = c.diagnostics.event(
            category=DiagnosticCategory.DOMAIN,
            event_type="strategy_decision",
            severity=DiagnosticSeverity.INFO,
            correlation=ui.diagnostic.correlation,
            source="shadow-composition",
        )
        self.assertEqual("trace-composition", event.correlation.trace_id)

    def test_persistence_candidate_flow(self) -> None:
        c = self.composition
        record = PersistenceRecord(
            "candidate-1",
            PersistenceKind.DOMAIN_STATE,
            StateSnapshot.new(state_type="session_candidate", owner="Session Domain", payload={"profile": "AGM"}),
        )
        c.persistence.save(record)
        candidate = c.persistence.restore_candidate(c.persistence.load("candidate-1"))
        self.assertFalse(candidate.verified)
        self.assertTrue(candidate.requires_fresh_verification)

    def test_execution_dependency_is_shadow_only(self) -> None:
        c = self.composition
        intent = ActuatorIntent.new(
            trace_id="trace-execution",
            source="shadow-composition",
            requested_operation=ActuatorOperation.SET_VOLTAGE,
            target=14.4,
            reason="shadow decision",
            owner="V2 runtime safety surface",
            trigger=ActuatorTrigger.START_REQUEST,
            rollback_policy=RollbackPolicy.SAFE_OFF,
            safety_context=SafetyContext("fresh", "held", "normal", "not_requested", "shadow"),
            verification_expectation=PhysicalVerificationExpectation("verified", True, "shadow"),
        )
        result = c.execution.dispatch_intent(intent, correlation={"operation": "set_voltage"})
        self.assertTrue(result.deferred)
        self.assertTrue(c.transport.ha.dispatch(result.request).deferred)
        self.assertTrue(c.transport.esp_direct.dispatch(result.request).deferred)

    def test_no_production_side_effect_imports(self) -> None:
        tree = ast.parse(MODULE.read_text(encoding="utf-8"), filename=str(MODULE))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append((node.module or "").lower())
        forbidden = ("bot", "telegram", "homeassistant", "esphome", "runtime.physical")
        self.assertEqual([], [name for name in imports if any(token in name for token in forbidden)])
        text = MODULE.read_text(encoding="utf-8")
        for call in ("output_on(", "output_off(", "set_voltage(", "set_current(", "asyncio.run"):
            self.assertNotIn(call, text)


if __name__ == "__main__":
    unittest.main()
