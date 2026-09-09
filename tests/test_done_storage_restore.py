import json
import os
import tempfile
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

from diagnostic_controller import DiagnosticProductionChargeControllerV2
from done_storage_restore import (
    DONE_COMPLETION_STORAGE,
    DONE_COMPLETION_TERMINAL,
    DONE_OUTPUT_OFF,
    DONE_OUTPUT_ON,
    _paused_done_resume_is_authorized,
    install_done_storage_restore,
    restore_allows_auto_enable,
)


class DummyHass:
    pass


class DoneStorageRestoreTests(unittest.TestCase):
    @staticmethod
    def _patch_session_file(path):
        stack = ExitStack()
        stack.enter_context(patch("charge_logic.SESSION_FILE", path))
        stack.enter_context(patch("charge_controller_v2.SESSION_FILE", path))
        stack.enter_context(patch("production_controller.SESSION_FILE", path))
        return stack

    @staticmethod
    def _installed_controller():
        controller = DiagnosticProductionChargeControllerV2(DummyHass(), authoritative=True)
        app = SimpleNamespace(charge_controller=controller)
        install_done_storage_restore(app)
        return app, controller

    def _write_storage_done(self, path):
        app, controller = self._installed_controller()
        controller.start("Ca/Ca", 72)
        controller.current_stage = controller.STAGE_SAFE_WAIT
        controller._safe_wait_target_v = 13.8
        controller._safe_wait_target_i = 1.0
        controller._done_transition_source_stage = controller.STAGE_SAFE_WAIT
        controller.current_stage = controller.STAGE_DONE
        # Simulate the exact historical hazard: the last physical readback is still
        # the old Mix program when SAFE_WAIT queues Storage programming + Output ON.
        controller._device_set_voltage = 16.5
        controller._device_set_current = 2.0
        with self._patch_session_file(path):
            controller._save_session(13.4, 0.0, 1.5)
        return app, controller

    def test_storage_done_persists_explicit_on_intent_and_canonical_storage_target(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = os.path.join(tempdir, "charge_session.json")
            _app, controller = self._write_storage_done(path)
            with open(path, "r", encoding="utf-8") as handle:
                document = json.load(handle)

            target_v, target_i = controller._storage_target()
            self.assertEqual(document["done_state_version"], 1)
            self.assertEqual(document["completion_kind"], DONE_COMPLETION_STORAGE)
            self.assertEqual(document["output_intent"], DONE_OUTPUT_ON)
            self.assertAlmostEqual(document["target_voltage"], target_v)
            self.assertAlmostEqual(document["target_current"], target_i)
            self.assertNotAlmostEqual(document["target_voltage"], 16.5)
            self.assertEqual(
                document["terminal_metadata"]["completion_kind"],
                DONE_COMPLETION_STORAGE,
            )
            self.assertEqual(document["terminal_metadata"]["output_intent"], DONE_OUTPUT_ON)

    def test_direct_done_is_persisted_as_terminal_off(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = os.path.join(tempdir, "charge_session.json")
            app, controller = self._installed_controller()
            controller.start("Ca/Ca", 72)
            controller.current_stage = controller.STAGE_MIX
            controller.current_stage = controller.STAGE_DONE
            with self._patch_session_file(path):
                controller._save_session(16.4, 0.7, 1.5)
            with open(path, "r", encoding="utf-8") as handle:
                document = json.load(handle)

            self.assertEqual(document["completion_kind"], DONE_COMPLETION_TERMINAL)
            self.assertEqual(document["output_intent"], DONE_OUTPUT_OFF)
            self.assertFalse(app._restore_allows_auto_enable(controller))

    def test_explicit_storage_done_restore_reenables_only_existing_safe_enable_path(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = os.path.join(tempdir, "charge_session.json")
            self._write_storage_done(path)

            app, restored = self._installed_controller()
            with self._patch_session_file(path):
                ok, _ = restored.try_restore_session(
                    13.4,
                    0.0,
                    1.5,
                    output_is_on=False,
                    is_cv=False,
                    is_cc=False,
                )

            self.assertTrue(ok)
            self.assertEqual(restored.current_stage, restored.STAGE_DONE)
            self.assertEqual(restored._done_completion_kind, DONE_COMPLETION_STORAGE)
            self.assertEqual(restored._done_output_intent, DONE_OUTPUT_ON)
            self.assertTrue(app._restore_allows_auto_enable(restored))
            target_v, target_i = restored._storage_target()
            self.assertAlmostEqual(restored._get_target_v_i()[0], target_v)
            self.assertAlmostEqual(restored._get_target_v_i()[1], target_i)

    def test_legacy_or_ambiguous_done_restore_is_normalized_to_terminal_off(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = os.path.join(tempdir, "charge_session.json")
            self._write_storage_done(path)
            with open(path, "r", encoding="utf-8") as handle:
                document = json.load(handle)
            document.pop("done_state_version", None)
            document.pop("completion_kind", None)
            document.pop("output_intent", None)
            metadata = document.get("terminal_metadata")
            if isinstance(metadata, dict):
                metadata.pop("completion_kind", None)
                metadata.pop("output_intent", None)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(document, handle)

            app, restored = self._installed_controller()
            with self._patch_session_file(path):
                ok, _ = restored.try_restore_session(
                    13.4,
                    0.0,
                    1.5,
                    output_is_on=False,
                    is_cv=False,
                    is_cc=False,
                )

            self.assertTrue(ok)
            self.assertFalse(app._restore_allows_auto_enable(restored))
            self.assertEqual(restored._done_completion_kind, DONE_COMPLETION_TERMINAL)
            self.assertEqual(restored._done_output_intent, DONE_OUTPUT_OFF)
            with open(path, "r", encoding="utf-8") as handle:
                normalized = json.load(handle)
            self.assertEqual(normalized["completion_kind"], DONE_COMPLETION_TERMINAL)
            self.assertEqual(normalized["output_intent"], DONE_OUTPUT_OFF)

    def test_operator_pause_cannot_bypass_ambiguous_done_restore_guard(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = os.path.join(tempdir, "charge_session.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"stage": "Done", "saved_at": 1.0}, handle)
            idle = SimpleNamespace(current_stage="Idle", STAGE_DONE="Done", is_active=False)
            app = SimpleNamespace(_operator_pause_active=lambda: True)
            with patch("charge_logic.SESSION_FILE", path):
                self.assertFalse(_paused_done_resume_is_authorized(app, idle))

    def test_operator_pause_accepts_only_explicit_storage_done_document_before_restore(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = os.path.join(tempdir, "charge_session.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "stage": "Done",
                        "done_state_version": 1,
                        "completion_kind": DONE_COMPLETION_STORAGE,
                        "output_intent": DONE_OUTPUT_ON,
                    },
                    handle,
                )
            idle = SimpleNamespace(current_stage="Idle", STAGE_DONE="Done", is_active=False)
            app = SimpleNamespace(_operator_pause_active=lambda: True)
            with patch("charge_logic.SESSION_FILE", path):
                self.assertTrue(_paused_done_resume_is_authorized(app, idle))

    def test_operator_pause_blocks_already_restored_terminal_done(self):
        terminal_done = SimpleNamespace(
            current_stage="Done",
            STAGE_DONE="Done",
            is_active=True,
            _done_outcome_authoritative=True,
            _done_completion_kind=DONE_COMPLETION_TERMINAL,
            _done_output_intent=DONE_OUTPUT_OFF,
        )
        app = SimpleNamespace(_operator_pause_active=lambda: True)
        self.assertFalse(_paused_done_resume_is_authorized(app, terminal_done))

    def test_non_done_restore_guard_contract_is_unchanged(self):
        active = SimpleNamespace(
            current_stage="Mix Mode",
            STAGE_DONE="Done",
            STAGE_COOLING="Cooling",
        )
        cooling = SimpleNamespace(
            current_stage="Cooling",
            STAGE_DONE="Done",
            STAGE_COOLING="Cooling",
        )
        unknown_done = SimpleNamespace(
            current_stage="Done",
            STAGE_DONE="Done",
            STAGE_COOLING="Cooling",
        )
        self.assertTrue(restore_allows_auto_enable(active))
        self.assertFalse(restore_allows_auto_enable(cooling))
        self.assertFalse(restore_allows_auto_enable(unknown_done))


if __name__ == "__main__":
    unittest.main()
