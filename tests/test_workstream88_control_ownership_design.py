import unittest
from pathlib import Path


DOC = Path(__file__).parents[1] / "docs" / "RD6018_STOP_PAUSE_EMERGENCY_OWNERSHIP_MODEL.md"


class Workstream88DesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")

    def test_all_three_authorities_are_defined(self):
        for authority in ("StopAuthority", "PauseAuthority", "EmergencyAuthority"):
            self.assertIn(authority, self.text)

    def test_current_v2_physical_owner_is_preserved(self):
        self.assertIn("Владелец физического OFF остаётся V2", self.text)
        self.assertIn("V2 safety/edge boundary", self.text)

    def test_lifecycle_and_physical_confirmation_are_separate(self):
        self.assertIn("Lifecycle event не подменяет physical confirmation", self.text)
        self.assertIn("verified readback", self.text)
        self.assertIn("failed/unknown event", self.text)

    def test_pause_semantics_are_non_terminal_and_recoverable(self):
        self.assertIn("не terminal STOP", self.text)
        self.assertIn("preserve session identity", self.text)
        self.assertIn("safety/readback", self.text)

    def test_emergency_is_fail_closed(self):
        self.assertIn("не восстанавливать output автоматически", self.text)
        self.assertIn("консервативным", self.text)

    def test_no_production_integration(self):
        for phrase in ("не создавать `StopAuthority`", "не подключать executor", "не выполнять реальные STOP"):
            self.assertIn(phrase, self.text)


if __name__ == "__main__":
    unittest.main()
