import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
DOC = ROOT / "docs" / "RD6018_V2_V3_START_OWNERSHIP_BRIDGE_MODEL.md"


class Workstream87DesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")

    def test_current_v2_owner_is_recorded(self):
        self.assertIn("DiagnosticProductionChargeControllerV2", self.text)
        self.assertIn("SafeOutputCoordinator", self.text)

    def test_single_authority_and_duplicate_guard_are_defined(self):
        self.assertIn("единственный StartAuthority", self.text)
        self.assertIn("idempotency key", self.text)
        self.assertIn("не более одного accepted START", self.text)

    def test_identity_handoff_is_complete(self):
        for field in ("session_id", "trace_id", "graph_session_id", "program_id"):
            self.assertIn(f"`{field}`", self.text)

    def test_rollback_remains_v2(self):
        self.assertIn("Rollback owner остаётся V2", self.text)
        self.assertIn("V2_ROLLBACK", self.text)

    def test_design_has_no_activation_or_physical_wiring(self):
        for forbidden in ("не менять `v2_bot_ui._start_profile()`", "не подключать V3 executor", "не выполнять реальные START/STOP"):
            self.assertIn(forbidden, self.text)


if __name__ == "__main__":
    unittest.main()
