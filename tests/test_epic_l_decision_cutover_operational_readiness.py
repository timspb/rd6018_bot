"""EPIC L operational readiness tests; no live ownership or execution."""

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

from application.decision_cutover_operational_readiness import (
    ApprovalLifecycleState,
    DecisionCutoverOperationalReadinessModel,
    OperationalReadinessState,
)
from application.decision_cutover_readiness import Stage1SafetyGates


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "application" / "decision_cutover_operational_readiness.py"
DOC = ROOT / "docs" / "RD6018_DECISION_CUTOVER_OPERATIONAL_READINESS_MODEL.md"


def gates():
    return Stage1SafetyGates(True, True, True, True, True)


class EpicLDecisionCutoverOperationalReadinessTests(unittest.TestCase):
    def test_health_gates_and_ownership_visibility(self):
        model = DecisionCutoverOperationalReadinessModel()
        snapshot = model.evaluate_health(gates())
        self.assertEqual(OperationalReadinessState.READY, snapshot.state)
        self.assertEqual("V2", snapshot.current_decision_owner)
        self.assertEqual("V3", snapshot.candidate_owner)
        self.assertEqual("V2", snapshot.execution_owner)
        self.assertEqual("V2", snapshot.physical_owner)
        self.assertFalse(snapshot.live_ownership_changed)

    def test_approval_lifecycle_expiry_and_revoke(self):
        model = DecisionCutoverOperationalReadinessModel()
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        model.evaluate_health(gates(), timestamp=now)
        approved = model.approve(
            operator="operator-1", source="runbook", rollback_authority="V2",
            timestamp=now, expires_at=now + timedelta(hours=1),
        )
        self.assertEqual(ApprovalLifecycleState.APPROVED, approved.approval_state)
        self.assertEqual("V2", approved.current_decision_owner)
        revoked = model.revoke(source="operator-1", reason="manual disable", timestamp=now + timedelta(minutes=1))
        self.assertEqual(ApprovalLifecycleState.REVOKED, revoked.approval_state)
        self.assertEqual(OperationalReadinessState.REVOKED, revoked.state)
        self.assertEqual("stage1_approval_revoked", revoked.audit_trail[-1].event_type)

        model.evaluate_health(gates(), timestamp=now)
        model.approve(operator="operator-1", source="runbook", rollback_authority="V2", timestamp=now, expires_at=now + timedelta(minutes=1))
        expired = model.expire(timestamp=now + timedelta(minutes=2))
        self.assertEqual(ApprovalLifecycleState.EXPIRED, expired.approval_state)
        self.assertEqual(OperationalReadinessState.EXPIRED, expired.state)

    def test_emergency_rollback_visibility(self):
        model = DecisionCutoverOperationalReadinessModel()
        model.evaluate_health(gates())
        model.approve(operator="operator-1", source="runbook", rollback_authority="V2", expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
        rolled = model.disable_v3_decision(source="watchdog", reason="health loss")
        self.assertEqual(OperationalReadinessState.ROLLED_BACK, rolled.state)
        self.assertEqual("V2", rolled.current_decision_owner)
        self.assertEqual("V2", rolled.execution_owner)
        self.assertEqual("V2", rolled.physical_owner)
        self.assertEqual("emergency_decision_rollback", rolled.audit_trail[-1].event_type)
        self.assertFalse(rolled.live_ownership_changed)

    def test_no_execution_calls_or_forbidden_imports(self):
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

    def test_document_covers_operational_contract(self):
        text = DOC.read_text(encoding="utf-8")
        for term in ("Operator visibility", "Approval lifecycle", "Emergency controls", "Audit trail", "Health gates", "LIVE_OWNERSHIP_UNCHANGED"):
            self.assertIn(term, text)


if __name__ == "__main__":
    unittest.main()
