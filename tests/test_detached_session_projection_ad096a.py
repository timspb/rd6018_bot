"""Detached canonical session projection parity; no hardware or live services."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pb_domain import ChargeIntent
from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.charge.programs.native_recipe_session import (
    SESSION_KEY, select_native_recipe_version,
)

from charge_controller import ManagedChargeController
from runtime.charge.persistence import (
    DONE_COMPLETION_TERMINAL,
    DONE_OUTPUT_OFF,
    project_session_document,
    save_session,
)
from runtime.charge.strategy.main_current_guard import MainCurrentGuard


class _NoHardware:
    pass


class DetachedSessionProjectionTests(unittest.TestCase):
    def _host(self, *, terminal=False, guard=False):
        host = ManagedChargeController(_NoHardware())
        with patch('charge_controller.clear_session_file'):
            host.start(ManagedChargeController.PROFILE_EFB, 72)
        host.current_stage = host.STAGE_DONE if terminal else host.STAGE_MAIN
        host.stage_start_time = 1234.0
        host.total_start_time = 1200.0
        host._v2_trace_session_id = "projection-session"
        host._v2_trace_started_at = 1200.0
        host._v2_battery_id = "projection-battery"
        host._device_set_voltage = None
        host._device_set_current = None
        if guard:
            host._main_current_guard = MainCurrentGuard.start(
                session_id="projection-session", battery_id="projection-battery",
                segment_id="main-1", capacity_ah=72, recipe_initial_current_a=7.2,
            )
        return host

    def test_projection_matches_written_active_document_and_keeps_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            path = str(Path(root) / "charge_session.json")
            prior = {"target_voltage": 14.4, "target_current": 7.0,
                     "terminal_metadata": {"voltage": 13.2, "current": 0.4, "ah": 5}}
            Path(path).write_text(json.dumps(prior), encoding="utf-8")
            original = Path(path).read_bytes()
            drafts = NativeRecipeDraftLibrary(Path(root) / "drafts")
            drafts.save("projection-recipe", 1, {
                "schema": 1, "base_recipe_id": "native_efb_normal",
                "execution_kind": "native_authority",
                "overrides": {"charge.main.efb_voltage_v": 14.6},
            })
            selection = select_native_recipe_version(
                drafts, "projection-recipe", 1, profile="EFB", intent="normal",
            )
            projected_host = self._host(guard=True)
            projected_host._v2_intent = ChargeIntent.NORMAL
            projected_host._native_recipe_session_selection = selection
            with patch("runtime.charge.persistence.time.time", return_value=2000.0):
                candidate = project_session_document(
                    projected_host, 14.2, 0.6, 8.0, session_file=path,
                )
                self.assertEqual(Path(path).read_bytes(), original)
                save_session(projected_host, 14.2, 0.6, 8.0, session_file=path)
            written = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertEqual(candidate, written)
            self.assertEqual(candidate["target_voltage"], 14.4)
            self.assertEqual(candidate["target_current"], 7.0)
            self.assertIn("main_current_guard_v1", candidate)
            self.assertEqual(candidate["v2_trace_session_id"], "projection-session")
            self.assertEqual(candidate[SESSION_KEY], selection.to_document())

    def test_terminal_metadata_falls_back_to_prior_positive_measurements(self):
        with tempfile.TemporaryDirectory() as root:
            path = str(Path(root) / "charge_session.json")
            prior = {"terminal_metadata": {"voltage": 13.25, "current": 0.35, "ah": 9.0}}
            Path(path).write_text(json.dumps(prior), encoding="utf-8")
            host = self._host(terminal=True)
            with patch("runtime.charge.persistence.time.time", return_value=2000.0):
                candidate = project_session_document(
                    host, 0.0, float("nan"), 0.0, session_file=path,
                )
            self.assertEqual(candidate["terminal_metadata"]["voltage"], 13.25)
            self.assertEqual(candidate["terminal_metadata"]["current"], 0.35)
            self.assertEqual(candidate["terminal_metadata"]["ah"], 9.0)
            self.assertEqual(candidate["completion_kind"], DONE_COMPLETION_TERMINAL)
            self.assertEqual(candidate["output_intent"], DONE_OUTPUT_OFF)

    def test_done_normalization_and_previous_setpoint_fallback_match_writer(self):
        with tempfile.TemporaryDirectory() as root:
            path = str(Path(root) / "charge_session.json")
            Path(path).write_text(json.dumps({"target_voltage": 13.6,
                                              "target_current": 1.25}), encoding="utf-8")
            projected = self._host(terminal=True)
            with patch("runtime.charge.persistence.time.time", return_value=2000.0):
                candidate = project_session_document(projected, 14.4, 0.5, 3,
                                                     session_file=path)
                save_session(projected, 14.4, 0.5, 3, session_file=path)
            self.assertEqual(candidate, json.loads(Path(path).read_text(encoding="utf-8")))
            self.assertEqual(candidate["target_voltage"], 13.6)
            self.assertEqual(candidate["target_current"], 1.25)
            self.assertTrue(projected._done_outcome_authoritative)


if __name__ == "__main__":
    unittest.main()
