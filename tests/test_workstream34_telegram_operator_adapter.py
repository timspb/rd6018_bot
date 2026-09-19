import ast
import unittest
from pathlib import Path

from application.active_session_parity import ActiveSessionParityObserver
from application.operator_dashboard_composer import OperatorDashboardComposer
from application.operator_explanation import DecisionExplanationEngine
from application.telegram_operator_adapter import TelegramOperatorViewAdapter


class Workstream34TelegramOperatorAdapterTests(unittest.TestCase):
    def dashboard(self):
        observer = ActiveSessionParityObserver()
        observation = observer.ingest(persisted={"state": "active", "stage": "mix", "request": {"battery_id": "Baic72"}}, telemetry={"voltage": 17.14, "current": 3.48, "temperature": 35.0, "source": "HA+ESP"}, rd={"phase": "mix"}, esphome={"output": True}, ha={"available": True})
        parity = observer.compare(observation, v2_state={"profile": "Baic72", "phase": "mix", "state": "active"}, v3_state={"profile": "Baic72", "phase": "mix", "state": "active"})
        from application.operator_runtime_view import OperatorRuntimeViewComposer
        runtime = OperatorRuntimeViewComposer().compose(observation=observation, parity=parity, shadow={"stale_sources": ("HA",), "lease": {"armed": True}, "protection": {"code": 0}})
        explanation = DecisionExplanationEngine().explain(observation=observation, parity=parity, evidence={"safety_state": "NORMAL", "strategy": "MIX_HOLD", "reason": "Delta evidence", "expected_next_transition": "HoldCompleted", "transition_conditions": ("hold_complete",), "historical_faults": ("old emergency marker",)})
        return OperatorDashboardComposer().compose(runtime_view=runtime, explanation=explanation, canary={"status": "BLOCKED", "blockers": ("CB-EVIDENCE-001",)}, timestamp=100)

    def test_dashboard_rendering(self):
        text = TelegramOperatorViewAdapter().format(self.dashboard())
        self.assertIn("Baic72", text)
        self.assertIn("17.14 V", text)
        self.assertIn("3.48 A", text)
        self.assertIn("59.65 W", text)
        self.assertIn("MIX_HOLD", text)

    def test_unknown_and_stale_are_visible(self):
        state = self.dashboard()
        from dataclasses import replace
        text = TelegramOperatorViewAdapter().format(replace(state, telemetry=replace(state.telemetry, voltage=None), timeline=replace(state.timeline, session_id="UNKNOWN")))
        self.assertIn("UNKNOWN", text)
        self.assertIn("stale: HA", text)

    def test_historical_fault_and_control_boundary_are_visible(self):
        text = TelegramOperatorViewAdapter().format(self.dashboard())
        self.assertIn("historical: old emergency marker", text)
        self.assertIn("CONTROL: недоступен", text)
        self.assertIn("canary: BLOCKED", text)

    def test_no_handlers_or_source_clients(self):
        source = (Path(__file__).resolve().parents[1] / "application" / "telegram_operator_adapter.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        self.assertFalse(imports & {"aiogram", "aiohttp", "aioesphomeapi", "paramiko", "serial", "requests"})
        for token in ("callback", "start_handler", "stop_handler", "output_on", "output_off", "turn_on", "turn_off", "lease_renew", "send_command"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
