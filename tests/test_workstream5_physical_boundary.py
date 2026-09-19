import ast
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from application.physical_boundary_validation import (
    CapabilityStatus,
    LeaseParityStatus,
    ReadbackVerificationModel,
    VerificationStatus,
    current_lease_parity_model,
    physical_execution_capability_map,
    safety_physical_boundary_report,
)


ROOT = Path(__file__).resolve().parents[1]


class Workstream5PhysicalBoundaryTests(unittest.TestCase):
    def test_capability_map_covers_all_operations_and_is_not_live(self):
        capabilities = physical_execution_capability_map()
        self.assertEqual({"OUTPUT_ON", "OUTPUT_OFF", "SET_VOLTAGE", "SET_CURRENT", "STOP", "CONTAINMENT"}, {item.operation for item in capabilities})
        self.assertTrue(all(item.status is CapabilityStatus.BLOCKED for item in capabilities))
        self.assertTrue(all("not connected" in item.adapter.lower() for item in capabilities))

    def test_readback_missing_unavailable_stale_wrong_and_success(self):
        now = datetime.now(timezone.utc)
        missing = ReadbackVerificationModel.verify(expected=14.7, observed=None, observed_at=None, now=now, timeout_s=5)
        unavailable = ReadbackVerificationModel.verify(expected=14.7, observed=14.7, observed_at=None, now=now, timeout_s=5)
        stale = ReadbackVerificationModel.verify(expected=14.7, observed=14.7, observed_at=now - timedelta(seconds=6), now=now, timeout_s=5)
        wrong = ReadbackVerificationModel.verify(expected=14.7, observed=14.2, observed_at=now, now=now, timeout_s=5, tolerance=0.05)
        success = ReadbackVerificationModel.verify(expected=14.7, observed=14.72, observed_at=now, now=now, timeout_s=5, tolerance=0.05)
        self.assertEqual(VerificationStatus.MISSING, missing.status)
        self.assertEqual(VerificationStatus.UNAVAILABLE, unavailable.status)
        self.assertEqual(VerificationStatus.STALE, stale.status)
        self.assertEqual(VerificationStatus.MISMATCH, wrong.status)
        self.assertEqual(VerificationStatus.VERIFIED, success.status)

    def test_lease_parity_preserves_current_owner_and_fail_safe(self):
        model = current_lease_parity_model()
        self.assertEqual("ESPHome/edge dead-man", model.current_owner)
        self.assertEqual(900.0, model.ttl_s)
        self.assertEqual("CONTAINMENT_REQUIRED", model.validate(status=LeaseParityStatus.EXPIRED))
        self.assertEqual("UNKNOWN_REQUIRES_FAIL_SAFE", model.validate(status=LeaseParityStatus.UNAVAILABLE))
        self.assertEqual("DUPLICATE_OWNER", model.validate(status=LeaseParityStatus.ACTIVE, owners=("V2", "V3")))

    def test_safety_boundary_is_traceable_and_nonphysical(self):
        report = safety_physical_boundary_report()
        self.assertEqual({"DETECTION", "SAFETY_DECISION", "CONTAINMENT", "EXECUTION", "VERIFICATION"}, {item.stage for item in report})
        self.assertTrue(all(item.trace_required for item in report))
        self.assertNotIn("physical", " ".join(item.status.lower() for item in report))

    def test_validation_modules_do_not_construct_hardware(self):
        path = ROOT / "application" / "physical_boundary_validation.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertTrue(all(not any(name in item for name in ("hass", "esphome", "runtime", "physical")) for item in imports))


if __name__ == "__main__":
    unittest.main()
