import unittest
from types import SimpleNamespace

from done_storage_restore import (
    DONE_COMPLETION_STORAGE,
    DONE_OUTPUT_ON,
    restore_allows_auto_enable,
)


class DoneStorageRestoreContractTests(unittest.TestCase):
    def test_done_requires_authoritative_storage_intent(self):
        controller = SimpleNamespace(
            current_stage="Done",
            STAGE_DONE="Done",
            _done_outcome_authoritative=True,
            _done_completion_kind=DONE_COMPLETION_STORAGE,
            _done_output_intent=DONE_OUTPUT_ON,
        )
        self.assertTrue(restore_allows_auto_enable(controller))

    def test_done_without_storage_intent_is_fail_closed(self):
        controller = SimpleNamespace(
            current_stage="Done",
            STAGE_DONE="Done",
            _done_outcome_authoritative=True,
            _done_completion_kind="terminal",
            _done_output_intent="off",
        )
        self.assertFalse(restore_allows_auto_enable(controller))

    def test_cooling_restore_remains_blocked(self):
        controller = SimpleNamespace(
            current_stage="Cooling",
            STAGE_DONE="Done",
            STAGE_COOLING="Cooling",
        )
        self.assertFalse(restore_allows_auto_enable(controller))

    def test_active_non_done_restore_keeps_existing_path(self):
        controller = SimpleNamespace(
            current_stage="Main",
            STAGE_DONE="Done",
            STAGE_COOLING="Cooling",
        )
        self.assertTrue(restore_allows_auto_enable(controller))


if __name__ == "__main__":
    unittest.main()
