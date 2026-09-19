import ast
import unittest
from pathlib import Path

from v3_core.canary_readiness import (
    BlockerType,
    CanaryApprovalGate,
    CanaryMode,
    CanaryRollbackModel,
    ReadinessStatus,
    RollbackTrigger,
    default_readiness_matrix,
    canary_modes,
)


ROOT = Path(__file__).resolve().parents[1]


class Workstream16CanaryReadinessTests(unittest.TestCase):
    def test_matrix_generation_and_blockers(self):
        matrix = default_readiness_matrix()
        self.assertEqual(ReadinessStatus.BLOCKED, matrix.status)
        self.assertTrue(matrix.blockers)
        self.assertTrue(all(item.evidence and item.owner for item in matrix.items))

    def test_modes_do_not_implicitly_transfer_ownership(self):
        modes = canary_modes()
        self.assertEqual(CanaryMode.SHADOW_ONLY, modes[0].mode)
        self.assertIn("owner", modes[0].v2_role)
        self.assertIn("observe", modes[0].v3_role)
        self.assertIn("approval", modes[2].entry)

    def test_rollback_conditions(self):
        model = CanaryRollbackModel(tuple(RollbackTrigger))
        self.assertTrue(model.requires_rollback(RollbackTrigger.LEASE_FAILURE))
        self.assertIn("preserve evidence", model.actions)

    def test_approval_lifecycle_and_expiry_fields(self):
        gate = CanaryApprovalGate("operator", ("shadow-pass",), approved_at=1.0, expires_at=2.0)
        self.assertTrue(gate.approved)
        self.assertFalse(gate.revoke().approved)

    def test_blocker_taxonomy_and_no_activation_symbols(self):
        self.assertEqual("TYPE_C_VALIDATION", BlockerType.VALIDATION.value)
        source = (ROOT / "v3_core" / "canary_readiness.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import) and node.names}
        self.assertFalse(imports & {"aiohttp", "paramiko", "requests", "esphome", "serial"})
        for token in ("output_on", "output_off", "set_voltage", "set_current", "controller.start", "controller.stop"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
