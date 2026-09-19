import ast
import unittest
from pathlib import Path

from application.canary_preflight import PreflightStatus
from application.canary_preflight_live import CurrentPreflightContext, LiveCanaryPreflightEvaluator
from v3_core.canary_readiness import CanaryApprovalGate, default_readiness_matrix
from v3_core.observability import HealthStatus, SystemHealthSnapshot
from v3_core.shadow_runtime_evidence import ShadowEvidenceBundle


ROOT = Path(__file__).resolve().parents[1]


def healthy():
    return SystemHealthSnapshot(*([HealthStatus.HEALTHY] * 8))


class Workstream18LivePreflightTests(unittest.TestCase):
    def context(self, *, evidence=True, approval=True, lease=None, external=None):
        return CurrentPreflightContext(
            timestamp=110.0,
            system_health=healthy(),
            evidence=ShadowEvidenceBundle("e", "o", "s", "t", 100.0) if evidence else None,
            diagnostics=("diagnostic",),
            readiness_matrix=default_readiness_matrix(),
            active_blockers=(),
            approval=CanaryApprovalGate("operator", ("evidence",), approved_at=90.0, expires_at=200.0) if approval else None,
            rollback_ready=True,
            rollback_owner="operator",
            external_availability=external or {"HA": "PASS", "telemetry": "PASS", "ESPHome": "PASS", "RD": "PASS"},
            lease_observation=lease or {"owner": "V2", "active": True, "tripped": False, "remaining_s": 880.0, "modbus_age_s": 2.0, "armed_age_s": 2.0},
        )

    def test_live_context_blocks_on_matrix_and_missing_approval(self):
        result = LiveCanaryPreflightEvaluator().evaluate(self.context(approval=False))
        self.assertEqual(PreflightStatus.BLOCKED, result.status)
        self.assertTrue(any("approval" in blocker for blocker in result.blockers))

    def test_stale_evidence_blocks(self):
        context = self.context()
        context = CurrentPreflightContext(**{**context.__dict__, "timestamp": 1101.0})
        self.assertEqual(PreflightStatus.BLOCKED, LiveCanaryPreflightEvaluator().evaluate(context).status)

    def test_lease_and_external_failure_block(self):
        result = LiveCanaryPreflightEvaluator().evaluate(self.context(
            lease={"owner": "V2", "active": True, "tripped": False, "remaining_s": 880.0, "modbus_age_s": 2.0, "armed_age_s": 3600.0},
            external={"HA": "PASS", "ESPHome": "NOT_VALIDATED", "RD": "PARTIAL", "telemetry": "PASS"},
        ))
        self.assertEqual(PreflightStatus.BLOCKED, result.status)
        self.assertTrue(any("stale" in blocker for blocker in result.blockers))
        self.assertTrue(any("external" in blocker for blocker in result.blockers))

    def test_synthetic_allowed_path_has_no_execution(self):
        context = self.context()
        context = CurrentPreflightContext(**{**context.__dict__, "readiness_matrix": type(default_readiness_matrix())(())})
        result = LiveCanaryPreflightEvaluator().evaluate(context)
        self.assertEqual(PreflightStatus.ALLOWED, result.status)

    def test_evaluator_is_read_only_and_has_no_physical_imports(self):
        source = (ROOT / "application" / "canary_preflight_live.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import) and node.names}
        self.assertFalse(imports & {"aiohttp", "paramiko", "requests", "esphome", "serial"})
        for token in ("output_on", "output_off", "set_voltage", "set_current", "controller.start", "controller.stop"):
            self.assertNotIn(token, source)
        self.assertIn("live_canary_preflight", (ROOT / "v3_core" / "observability.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
