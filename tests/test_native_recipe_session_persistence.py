"""Native recipe snapshot uses the existing canonical session writer and restore."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pb_domain import ChargeIntent
from production_controller import create_production_charge_host
from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.charge.programs.native_recipe_session import (
    SESSION_KEY, select_native_recipe_version,
)


class _NoHardware:
    pass


class NativeRecipeSessionPersistenceTests(unittest.TestCase):
    def _host(self):
        host = create_production_charge_host(_NoHardware())
        host.start("EFB", 72)
        host._v2_intent = ChargeIntent.NORMAL
        host._v2_trace_session_id = "native-snapshot-session"
        host._v2_trace_started_at = 17000.0
        host.current_stage = host.STAGE_MAIN
        host.stage_start_time = 19900.0
        return host

    def test_snapshot_survives_save_and_restore_without_library_access(self):
        with tempfile.TemporaryDirectory() as root:
            path = str(Path(root) / "charge_session.json")
            drafts = NativeRecipeDraftLibrary(Path(root) / "drafts")
            drafts.save("my_efb", 1, {
                "schema": 1, "base_recipe_id": "native_efb_normal",
                "execution_kind": "native_authority",
                "overrides": {"charge.main.efb_voltage_v": 14.6},
            })
            selected = select_native_recipe_version(
                drafts, "my_efb", 1, profile="EFB", intent="normal")
            host = self._host()
            host._native_recipe_session_selection = selected
            with patch("charge_controller.SESSION_FILE", path), patch(
                "charge_controller.time.time", return_value=20000.0
            ):
                host._save_session(14.6, 0.3, 2.0)
                recorded = json.loads(Path(path).read_text(encoding="utf8"))
                self.assertEqual(recorded[SESSION_KEY], selected.to_document())
                drafts.save("my_efb", 2, {
                    "schema": 1, "base_recipe_id": "native_efb_normal",
                    "execution_kind": "native_authority",
                    "overrides": {"charge.main.efb_voltage_v": 14.5},
                })
                fresh = create_production_charge_host(_NoHardware())
                ok, why = fresh.try_restore_session(
                    14.6, 0.3, 2.0, output_is_on=True, is_cv=True, is_cc=False,
                )
            self.assertTrue(ok, why)
            self.assertEqual(fresh._native_recipe_session_selection, selected)
            self.assertEqual(dict(fresh._native_recipe_session_selection.overrides),
                             {"charge.main.efb_voltage_v": 14.6})

    def test_modified_persisted_recipe_refuses_restore_before_state_mutation(self):
        with tempfile.TemporaryDirectory() as root:
            path = str(Path(root) / "charge_session.json")
            drafts = NativeRecipeDraftLibrary(Path(root) / "drafts")
            drafts.save("copy", 1, {
                "schema": 1, "base_recipe_id": "native_efb_normal",
                "execution_kind": "native_authority", "overrides": {},
            })
            host = self._host()
            host._native_recipe_session_selection = select_native_recipe_version(
                drafts, "copy", 1, profile="EFB", intent="normal")
            with patch("charge_controller.SESSION_FILE", path), patch(
                "charge_controller.time.time", return_value=20000.0
            ):
                host._save_session(14.6, 0.3, 2.0)
                data = json.loads(Path(path).read_text(encoding="utf8"))
                data[SESSION_KEY]["version"] = 999
                Path(path).write_text(json.dumps(data), encoding="utf8")
                fresh = create_production_charge_host(_NoHardware())
                previous = fresh.current_stage
                ok, reason = fresh.try_restore_session(
                    14.6, 0.3, 2.0, output_is_on=True, is_cv=True, is_cc=False,
                )
            self.assertFalse(ok)
            self.assertIn("Native recipe session selection invalid", reason)
            self.assertEqual(fresh.current_stage, previous)

    def test_unselected_new_session_does_not_inherit_pinned_recipe(self):
        from runtime.charge.session_atomic import complete_session_document
        host = self._host()
        host._native_recipe_session_selection = None
        output = complete_session_document(
            host, {"stage": host.STAGE_MAIN},
            previous={SESSION_KEY: {"old": "must not be inherited"}},
            now_s=20000.0,
        )
        self.assertNotIn(SESSION_KEY, output)

