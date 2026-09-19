import ast
import unittest
from datetime import datetime, timezone
from pathlib import Path

from v3_core.observability import (
    DiagnosticCategory,
    DiagnosticHistory,
    DiagnosticHistoryQuery,
    DiagnosticsDomain,
    DiagnosticSeverity,
    HealthStatus,
    OperatorAlert,
    OperatorDashboardSnapshot,
    SystemHealthSnapshot,
    TraceContext,
)


ROOT = Path(__file__).resolve().parents[1]


class Workstream9ObservabilityTests(unittest.TestCase):
    def test_diagnostic_event_creation_and_trace_continuity(self):
        context = TraceContext.create("session-9")
        domain = DiagnosticsDomain()
        event = domain.emit(context=context, severity=DiagnosticSeverity.INFO, category=DiagnosticCategory.DOMAIN, source="domain", component="phase", message="phase changed")
        self.assertEqual("session-9", event.session_id)
        self.assertEqual(context.trace_id, event.trace_id)
        self.assertEqual(context.correlation_id, event.correlation_id)

    def test_missing_trace_is_rejected(self):
        with self.assertRaises(ValueError):
            TraceContext("s", "", "c")

    def test_cross_module_child_correlation(self):
        root = TraceContext.create("s")
        child = root.child()
        self.assertEqual(root.session_id, child.session_id)
        self.assertEqual(root.trace_id, child.trace_id)
        self.assertNotEqual(root.correlation_id, child.correlation_id)

    def test_health_aggregation(self):
        snapshot = SystemHealthSnapshot(HealthStatus.HEALTHY, HealthStatus.HEALTHY, HealthStatus.WARNING, HealthStatus.HEALTHY, HealthStatus.HEALTHY, HealthStatus.HEALTHY, HealthStatus.HEALTHY, HealthStatus.HEALTHY)
        self.assertEqual(HealthStatus.WARNING, snapshot.overall)
        failed = SystemHealthSnapshot(HealthStatus.FAILED, *([HealthStatus.HEALTHY] * 7))
        self.assertEqual(HealthStatus.FAILED, failed.overall)

    def test_dashboard_snapshot_is_read_model(self):
        health = SystemHealthSnapshot(*([HealthStatus.HEALTHY] * 8))
        snapshot = OperatorDashboardSnapshot({"session": "s"}, (), health, "NORMAL", {"last": "VERIFIED"}, {"profile": "AGM"}, (), ())
        self.assertEqual("s", snapshot.current_charge["session"])
        self.assertEqual(HealthStatus.HEALTHY, snapshot.health.overall)

    def test_alert_lifecycle(self):
        alert = OperatorAlert("a", DiagnosticSeverity.ERROR, "safety", datetime.now(timezone.utc), "fault", "RD", "stop")
        self.assertFalse(alert.resolved)
        self.assertTrue(alert.resolve().resolved)

    def test_history_query_filters_session_and_severity(self):
        context = TraceContext.create("s1")
        domain = DiagnosticsDomain()
        domain.emit(context=context, severity=DiagnosticSeverity.INFO, category=DiagnosticCategory.DOMAIN, source="d", component="c", message="info")
        domain.emit(context=context, severity=DiagnosticSeverity.ERROR, category=DiagnosticCategory.SAFETY, source="s", component="c", message="error")
        result = DiagnosticHistory().query(domain.snapshot(), DiagnosticHistoryQuery(session_id="s1", minimum_severity=DiagnosticSeverity.WARNING))
        self.assertEqual(1, len(result))
        self.assertEqual(DiagnosticCategory.SAFETY, result[0].category)

    def test_safety_and_execution_events_are_visible(self):
        context = TraceContext.create("s")
        domain = DiagnosticsDomain()
        domain.emit(context=context, severity=DiagnosticSeverity.WARNING, category=DiagnosticCategory.SAFETY, source="safety", component="containment", message="containment")
        domain.emit(context=context, severity=DiagnosticSeverity.INFO, category=DiagnosticCategory.EXECUTION, source="execution", component="adapter", message="verified")
        categories = {event.category for event in domain.snapshot()}
        self.assertEqual({DiagnosticCategory.SAFETY, DiagnosticCategory.EXECUTION}, categories)

    def test_observability_module_has_no_physical_or_ui_callbacks(self):
        path = ROOT / "v3_core" / "observability.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertTrue(all(not any(token in item for token in ("runtime", "hass", "esphome", "physical", "application")) for item in imports))
        text = path.read_text(encoding="utf-8")
        for token in ("turn_on(", "turn_off(", "set_voltage(", "set_current(", "callback"):
            self.assertNotIn(token, text)


if __name__ == "__main__":
    unittest.main()
