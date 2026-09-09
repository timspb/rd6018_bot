import unittest
from types import SimpleNamespace

from bot_legacy import _restore_allows_auto_enable


class RestoreTerminalGuardTests(unittest.TestCase):
    def test_done_restore_cannot_auto_enable_output(self):
        controller = SimpleNamespace(current_stage="Done", STAGE_DONE="Done")
        self.assertFalse(_restore_allows_auto_enable(controller))

    def test_active_mix_restore_can_keep_existing_auto_resume_contract(self):
        controller = SimpleNamespace(current_stage="Mix Mode", STAGE_DONE="Done")
        self.assertTrue(_restore_allows_auto_enable(controller))

    def test_legacy_terminal_restore_is_also_blocked(self):
        controller = SimpleNamespace(current_stage="Done", STAGE_DONE="Done")
        self.assertFalse(_restore_allows_auto_enable(controller))

    def test_cooling_restore_cannot_auto_enable_output(self):
        controller = SimpleNamespace(
            current_stage="🌡 Остывание",
            STAGE_DONE="Done",
            STAGE_COOLING="🌡 Остывание",
        )
        self.assertFalse(_restore_allows_auto_enable(controller))


if __name__ == "__main__":
    unittest.main()
