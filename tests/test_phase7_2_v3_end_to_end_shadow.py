"""Phase 7.2 logical V3 pipeline validation; shadow only."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
import unittest

from application.actuator_intent import (
    ActuatorIntent,
    ActuatorOperation,
    ActuatorTrigger,
    PhysicalVerificationExpectation,
    RollbackPolicy,
    SafetyContext,
)
from application.charge_orchestration import ChargeApplicationService, TelemetrySnapshot
from application.configuration_model import ConfigurationModel, YamlSourceAdapter, default_configuration_authority
from application.diagnostics_domain import DiagnosticCategory, DiagnosticEvent, DiagnosticSeverity, TraceCorrelation
from application.execution_boundary import ContainmentResultRequest, ExecutionDispatcher
from application.intents import OperatorIntent, OperatorIntentKind
from application.transport_adapters_shadow import ESPDirectExecutionAdapter, HAExecutionAdapter
from application.actuator_intent_adapter import ActuatorIntentAdapter
from application.diagnostics_domain import DiagnosticsDomain
from runtime.charge import ProfileRegistry, SessionManager


ROOT = Path(__file__).resolve().parents[1]


def _telemetry(voltage: float = 13.8, current: float = 2.0, output_on: bool = False) -> TelemetrySnapshot:
    return TelemetrySnapshot(voltage, current, 23.0, output_on, datetime.now(timezone.utc))


def _safety(state: str = "normal") -> SafetyContext:
    return SafetyContext("fresh", "held", state, "not_requested", "phase7.2-shadow")


def _expectation(state: str = "unchanged") -> PhysicalVerificationExpectation:
    return PhysicalVerificationExpectation(state, True, "shadow-only")


class V3EndToEndShadowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.trace_id = "trace-phase7-2"
        self.correlation = TraceCorrelation(self.trace_id, "span-start", session_id="session-shadow")
        self.diagnostics = DiagnosticsDomain()
        self.dispatcher = ExecutionDispatcher()
        self.app = ChargeApplicationService(ProfileRegistry.with_defaults(), SessionManager())
        self.events: list[DiagnosticEvent] = []

    def _event(self, event_type: str, category: DiagnosticCategory = DiagnosticCategory.DOMAIN) -> DiagnosticEvent:
        event = self.diagnostics.event(
            category=category,
            event_type=event_type,
            severity=DiagnosticSeverity.INFO,
            correlation=self.correlation,
            source="phase7.2-shadow",
        )
        self.events.append(event)
        return event

    def test_complete_agm_pipeline_and_trace_continuity(self) -> None:
        start = OperatorIntent(
            OperatorIntentKind.START_CHARGE,
            "shadow-ui",
            "operator-1",
            {"profile": "AGM", "capacity_ah": 72, "session_id": "session-shadow"},
        )
        decision = self.app.handle(start, _telemetry())
        self.assertTrue(decision.accepted)
        self.assertEqual("active", decision.session.status.value)
        self.assertIsNotNone(decision.domain)
        self._event("session_state_changed")
        self._event("strategy_decision")

        domain_intent = decision.domain.intent
        self.assertIsNotNone(domain_intent)
        actuator = ActuatorIntent.new(
            trace_id=self.trace_id,
            source="v3-domain-shadow",
            requested_operation=ActuatorOperation.SET_VOLTAGE,
            target=domain_intent.voltage,
            reason=domain_intent.reason or "domain setpoint",
            owner="V2 runtime safety surface",
            trigger=ActuatorTrigger.START_REQUEST,
            rollback_policy=RollbackPolicy.SAFE_OFF,
            safety_context=_safety(),
            verification_expectation=_expectation("setpoint_verified"),
        )
        result = self.dispatcher.dispatch_intent(actuator, correlation={"operation": "set_voltage"})
        self.assertTrue(result.accepted and result.deferred)
        shadow = HAExecutionAdapter().dispatch(result.request)
        self.assertEqual((True, False, True), (shadow.accepted, shadow.rejected, shadow.deferred))
        self._event("execution_deferred", DiagnosticCategory.INFRASTRUCTURE)
        self.assertTrue(all(event.correlation.trace_id == self.trace_id for event in self.events))

    def test_telemetry_update_and_phase_transition_are_domain_only(self) -> None:
        start = OperatorIntent(OperatorIntentKind.START_CHARGE, "shadow", "operator", {"profile": "AGM", "capacity_ah": 72})
        self.assertTrue(self.app.handle(start, _telemetry()).accepted)
        update = self.app.handle(OperatorIntent(OperatorIntentKind.REFRESH, "shadow", "operator"), _telemetry(14.8, 0.2, True))
        self.assertTrue(update.accepted)
        self._event("phase_changed")
        self.assertEqual("phase_changed", self.events[-1].event_type)
        self.assertIsNone(update.domain.containment if update.domain else None)

    def test_stop_and_containment_are_deferred(self) -> None:
        start = OperatorIntent(OperatorIntentKind.START_CHARGE, "shadow", "operator", {"profile": "AGM", "capacity_ah": 72})
        self.app.handle(start, _telemetry())
        stop = self.app.handle(OperatorIntent(OperatorIntentKind.STOP_CHARGE, "shadow", "operator"), _telemetry())
        self.assertTrue(stop.accepted)
        self.assertIsNotNone(stop.domain)
        request = ContainmentResultRequest(
            trace_id=self.trace_id,
            source="v3-domain-shadow",
            trigger=stop.domain.containment.trigger,
            requested_action="output_off",
            owner="SafeOutputCoordinator",
            safety_context=_safety("containment_requested"),
            rollback_policy=RollbackPolicy.SAFE_OFF,
            verification_expectation=_expectation("off_confirmed"),
        )
        result = self.dispatcher.dispatch_containment(request, correlation={"operation": "output_off"})
        self.assertTrue(result.accepted and result.deferred)
        self.assertTrue(ESPDirectExecutionAdapter().dispatch(result.request).deferred)
        self._event("containment_requested")

    def test_transport_parity_and_invalid_safety_context(self) -> None:
        intent = ActuatorIntent.new(
            trace_id=self.trace_id,
            source="v3-domain-shadow",
            requested_operation=ActuatorOperation.SET_CURRENT,
            target=1.5,
            reason="shadow strategy",
            owner="V2 runtime safety surface",
            trigger=ActuatorTrigger.START_REQUEST,
            rollback_policy=RollbackPolicy.SAFE_OFF,
            safety_context=_safety(),
            verification_expectation=_expectation("setpoint_verified"),
        )
        result = self.dispatcher.dispatch_intent(intent, correlation={"operation": "set_current"})
        ha = HAExecutionAdapter().dispatch(result.request)
        esp = ESPDirectExecutionAdapter().dispatch(result.request)
        self.assertEqual(ha.reason.replace("ha-shadow", "adapter"), esp.reason.replace("esp-direct-shadow", "adapter"))

        blocked = ActuatorIntent.new(
            trace_id=self.trace_id,
            source="v3-domain-shadow",
            requested_operation=ActuatorOperation.OUTPUT_ON,
            target=True,
            reason="blocked test",
            owner="V2 runtime safety surface",
            trigger=ActuatorTrigger.START_REQUEST,
            rollback_policy=RollbackPolicy.SAFE_OFF,
            safety_context=_safety("blocked"),
            verification_expectation=_expectation("on"),
        )
        with self.assertRaises(ValueError):
            ActuatorIntentAdapter().adapt(blocked)

    def test_configuration_provenance_and_candidate_persistence_only(self) -> None:
        authority = default_configuration_authority()
        yaml_values = YamlSourceAdapter({
            "manual.main.voltage_v": "charge.manual.main.voltage_v",
            "limits.max_voltage_v": "safety.max_voltage_v",
        }).read(ROOT / "config" / "charge" / "manual.yaml")
        # limits is intentionally absent from this file; safety falls back to its documented default.
        model = ConfigurationModel.resolve(authority, (yaml_values,))
        self.assertEqual("yaml", model.value("charge.manual.main.voltage_v").source)
        self.assertEqual(18.0, model.get("safety.max_voltage_v"))
        candidate_state = {"session_id": "session-shadow", "status": "active", "persist": False}
        self.assertFalse(candidate_state["persist"])

    def test_shadow_modules_have_no_ha_or_esp_imports(self) -> None:
        for path in (ROOT / "application" / "transport_adapters_shadow.py", ROOT / "application" / "execution_boundary.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            modules = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules.extend(alias.name.lower() for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    modules.append((node.module or "").lower())
            self.assertEqual([], [module for module in modules if "ha" in module or "esp" in module or "telegram" in module])


if __name__ == "__main__":
    unittest.main()
