"""EPIC M decision canary tests; execution remains V2-owned."""

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

from application.decision_canary import (
    CanaryHealthSnapshot,
    CanaryState,
    DecisionCanaryController,
)


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "application" / "decision_canary.py"
DOC = ROOT / "docs" / "RD6018_DECISION_CANARY_MODEL.md"


class EpicMDecisionCanaryTests(unittest.TestCase):
    def test_state_transitions_and_ownership(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        controller = DecisionCanaryController()
        self.assertEqual(CanaryState.DISABLED, controller.snapshot().state)
        shadow = controller.enable_shadow(scope="battery-72", source="operator", timestamp=now)
        self.assertEqual(CanaryState.SHADOW, shadow.state)
        canary = controller.enter_canary(
            scope="battery-72", duration=timedelta(minutes=10), operator="op-1",
            source="runbook", rollback_authority="V2", health=CanaryHealthSnapshot(), timestamp=now,
        )
        self.assertEqual(CanaryState.CANARY, canary.state)
        self.assertEqual("V3", canary.decision_owner)
        self.assertEqual("V2", canary.execution_owner)
        self.assertEqual("V2", canary.physical_owner)
        active = controller.activate_decision(source="operator", timestamp=now)
        self.assertEqual(CanaryState.ACTIVE_DECISION, active.state)
        self.assertFalse(active.live_execution_ownership_changed)

    def test_expiry_rolls_back_to_v2(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        controller = DecisionCanaryController()
        controller.enable_shadow(scope="s1", source="test", timestamp=now)
        controller.enter_canary(
            scope="s1", duration=timedelta(minutes=1), operator="op", source="test",
            rollback_authority="V2", health=CanaryHealthSnapshot(), timestamp=now,
        )
        expired = controller.tick(timestamp=now + timedelta(minutes=1), source="timer")
        self.assertEqual(CanaryState.ROLLBACK, expired.state)
        self.assertEqual("V2", expired.decision_owner)
        self.assertEqual("canary_rollback", expired.audit_trail[-1].event_type)

    def test_blockers_activate_rollback(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        controller = DecisionCanaryController()
        controller.enable_shadow(scope="s1", source="test", timestamp=now)
        controller.enter_canary(
            scope="s1", duration=timedelta(minutes=5), operator="op", source="test",
            rollback_authority="V2", health=CanaryHealthSnapshot(), timestamp=now,
        )
        blocked = controller.observe_health(
            CanaryHealthSnapshot(telemetry_healthy=False, unexplained_divergence=True),
            source="health", timestamp=now + timedelta(seconds=1),
        )
        self.assertEqual(CanaryState.ROLLBACK, blocked.state)
        self.assertIn("telemetry_unhealthy", blocked.blockers)
        self.assertIn("unexplained_divergence", blocked.blockers)
        self.assertEqual("V2", blocked.execution_owner)

    def test_manual_rollback_and_history(self):
        controller = DecisionCanaryController()
        rolled = controller.rollback(source="operator", reason="emergency")
        self.assertEqual(CanaryState.ROLLBACK, rolled.state)
        self.assertEqual("V2", rolled.decision_owner)
        self.assertEqual("operator", rolled.audit_trail[-1].source)

    def test_no_execution_or_physical_imports(self):
        tree = ast.parse(MODULE.read_text(encoding="utf-8"), filename=str(MODULE))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append((node.module or "").lower())
        forbidden = ("controller", "execution", "hass", "homeassistant", "esphome", "lease", "transport", "physical", "output")
        self.assertEqual([], [name for name in imported if any(token in name for token in forbidden)])
        source = MODULE.read_text(encoding="utf-8")
        for token in ("dispatch(", "output_on(", "output_off(", "set_voltage(", "set_current(", "controller.start", "controller.stop"):
            self.assertNotIn(token, source)

    def test_document_covers_canary_contract(self):
        text = DOC.read_text(encoding="utf-8")
        for term in ("DISABLED", "SHADOW", "CANARY", "ACTIVE_DECISION", "ROLLBACK", "scope", "duration", "approval", "expiry", "rollback policy", "LIVE_EXECUTION_OWNERSHIP_UNCHANGED"):
            self.assertIn(term, text)


if __name__ == "__main__":
    unittest.main()
