import ast
import unittest
from pathlib import Path

from application.canary_preflight import CanaryPreflightValidator, PreflightStatus
from v3_core.canary_readiness import CanaryApprovalGate, GateSection, ReadinessItem, ReadinessStatus, V3CanaryReadinessMatrix
from v3_core.observability import HealthStatus, SystemHealthSnapshot
from v3_core.shadow_runtime_evidence import ShadowEvidenceBundle


ROOT = Path(__file__).resolve().parents[1]


def healthy():
    return SystemHealthSnapshot(*([HealthStatus.HEALTHY] * 8))


def matrix(status=ReadinessStatus.PASS):
    return V3CanaryReadinessMatrix((ReadinessItem(GateSection.ARCHITECTURE, "all", status, "test evidence", None if status is ReadinessStatus.PASS else "blocked", "test owner"),))


class Workstream17CanaryPreflightTests(unittest.TestCase):
    def valid_inputs(self):
        return dict(readiness_matrix=matrix(), current_health=healthy(), shadow_evidence=ShadowEvidenceBundle("e", "o", "s", "t", 100.0), diagnostics=("d1",), approval=CanaryApprovalGate("operator", ("evidence",), approved_at=90.0, expires_at=200.0), blocker_registry=(), now=110.0, rollback_ready=True, rollback_owner="operator")

    def test_all_checks_pass(self):
        result = CanaryPreflightValidator().validate(**self.valid_inputs())
        self.assertEqual(PreflightStatus.ALLOWED, result.status)
        self.assertFalse(result.blockers)

    def test_missing_evidence_blocks(self):
        values = self.valid_inputs()
        values["shadow_evidence"] = None
        self.assertEqual(PreflightStatus.BLOCKED, CanaryPreflightValidator().validate(**values).status)

    def test_stale_evidence_warning_and_block(self):
        values = self.valid_inputs()
        values["approval"] = CanaryApprovalGate("operator", ("evidence",), approved_at=90.0, expires_at=2000.0)
        values["now"] = 500.0
        result = CanaryPreflightValidator().validate(**values)
        self.assertEqual(PreflightStatus.WARNING, result.status)
        values["now"] = 1101.0
        self.assertEqual(PreflightStatus.BLOCKED, CanaryPreflightValidator().validate(**values).status)

    def test_safety_matrix_approval_and_rollback_block(self):
        values = self.valid_inputs()
        values["readiness_matrix"] = matrix(ReadinessStatus.BLOCKED)
        values["approval"] = None
        values["rollback_ready"] = False
        result = CanaryPreflightValidator().validate(**values)
        self.assertEqual(PreflightStatus.BLOCKED, result.status)
        self.assertGreaterEqual(len(result.blockers), 3)

    def test_snapshot_is_read_only_and_no_execution_imports(self):
        result = CanaryPreflightValidator().validate(**self.valid_inputs())
        snapshot = CanaryPreflightValidator.snapshot(result)
        self.assertEqual(result.status, snapshot.status)
        source = (ROOT / "application" / "canary_preflight.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import) and node.names}
        self.assertFalse(imports & {"aiohttp", "paramiko", "requests", "esphome", "serial"})
        for token in ("output_on", "output_off", "set_voltage", "set_current", "controller.start", "controller.stop"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
