import json
import os
import tempfile
import unittest
from unittest.mock import patch

from charge_controller import ManagedChargeController, FinalSafeWaitContinuation
from diagnostic_controller import DiagnosticProductionChargeController
from runtime.charge.persistence import DONE_COMPLETION_STORAGE, DONE_OUTPUT_ON


class DummyHass:
    pass


class FinalSafeWaitOutputTransactionTests(unittest.TestCase):
    def _controller_waiting_for_storage(self, session_file):
        controller = ManagedChargeController(DummyHass())
        controller.start("AGM", 90)
        controller._v2_trace_session_id = "session-final"
        controller.current_stage = controller.STAGE_MIX
        actions = {}
        with patch("charge_controller.SESSION_FILE", session_file), patch(
            "charge_controller.SESSION_FILE", session_file
        ):
            controller._enter_safe_wait_done(
                actions=actions,
                now=1000.0,
                voltage=16.2,
                current=0.5,
                temp=25.0,
                ah=10.0,
                reason="confirmed_delta_and_sticky_hold",
            )
        return controller, actions

    def test_storage_stage_commits_only_after_session_bound_verified_enable(self):
        with tempfile.TemporaryDirectory() as tempdir:
            session_file = os.path.join(tempdir, "charge_session.json")
            controller, actions = self._controller_waiting_for_storage(session_file)

            self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)
            self.assertTrue(actions["turn_off"])
            self.assertIsInstance(controller._final_safe_wait, FinalSafeWaitContinuation)

            transition_actions = {}
            with patch("charge_controller.SESSION_FILE", session_file), patch(
                "charge_controller.SESSION_FILE", session_file
            ):
                handled = controller._handle_safe_wait_stage_override(
                    now=1001.0,
                    voltage=13.2,
                    current=0.0,
                    temp=25.0,
                    ah=10.0,
                    actions=transition_actions,
                    output_is_on=False,
                )
                self.assertTrue(handled)
                self.assertTrue(transition_actions["turn_on"])
                self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)

                committed = controller.commit_verified_enable_transition(
                    transition_actions["verified_enable_transition"],
                    now=1002.0,
                    voltage=13.2,
                    current=0.0,
                    ah=10.0,
                )

            self.assertEqual(controller.current_stage, controller.STAGE_DONE)
            self.assertIsNone(controller._final_safe_wait)
            self.assertEqual(committed["log_event"], "START | V2_STORAGE_OUTPUT_VERIFIED")

    def test_failed_or_stale_storage_transition_keeps_safe_wait_pending(self):
        with tempfile.TemporaryDirectory() as tempdir:
            controller, _actions = self._controller_waiting_for_storage(
                os.path.join(tempdir, "charge_session.json")
            )
            transition_actions = {}
            controller._handle_safe_wait_stage_override(
                now=1001.0,
                voltage=13.2,
                current=0.0,
                temp=25.0,
                ah=10.0,
                actions=transition_actions,
                output_is_on=False,
            )
            stale_token = dict(transition_actions["verified_enable_transition"])
            stale_token["session_id"] = "different-session"

            self.assertIsNone(
                controller.commit_verified_enable_transition(
                    stale_token,
                    now=1002.0,
                    voltage=13.2,
                    current=0.0,
                    ah=10.0,
                )
            )
            self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)
            self.assertIsNotNone(controller._final_safe_wait)

    def test_unknown_output_state_never_requests_storage_enable(self):
        with tempfile.TemporaryDirectory() as tempdir:
            controller, _actions = self._controller_waiting_for_storage(
                os.path.join(tempdir, "charge_session.json")
            )
            actions = {}
            self.assertTrue(
                controller._handle_safe_wait_stage_override(
                    now=1001.0,
                    voltage=13.2,
                    current=0.0,
                    temp=25.0,
                    ah=10.0,
                    actions=actions,
                    output_is_on=None,
                )
            )
            self.assertNotIn("turn_on", actions)
            self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)

    def test_verified_final_transition_persists_storage_on_intent(self):
        with tempfile.TemporaryDirectory() as tempdir:
            session_file = os.path.join(tempdir, "charge_session.json")
            controller = DiagnosticProductionChargeController(
                DummyHass()
            )
            with patch("runtime.charge.persistence.SESSION_FILE", session_file), patch(
                "charge_controller.SESSION_FILE", session_file
            ), patch("production_controller.SESSION_FILE", session_file):
                controller.start("AGM", 90)
                controller._v2_trace_session_id = "session-final"
                controller.current_stage = controller.STAGE_MIX
                controller._enter_safe_wait_done(
                    actions={},
                    now=1000.0,
                    voltage=16.2,
                    current=0.5,
                    temp=25.0,
                    ah=10.0,
                    reason="confirmed_delta_and_sticky_hold",
                )
                transition_actions = {}
                controller._handle_safe_wait_stage_override(
                    now=1001.0,
                    voltage=13.2,
                    current=0.0,
                    temp=25.0,
                    ah=10.0,
                    actions=transition_actions,
                    output_is_on=False,
                )
                controller.commit_verified_enable_transition(
                    transition_actions["verified_enable_transition"],
                    now=1002.0,
                    voltage=13.2,
                    current=0.0,
                    ah=10.0,
                )
                with open(session_file, "r", encoding="utf-8") as handle:
                    saved = json.load(handle)

            self.assertEqual(controller.current_stage, controller.STAGE_DONE)
            self.assertEqual(saved["completion_kind"], DONE_COMPLETION_STORAGE)
            self.assertEqual(saved["output_intent"], DONE_OUTPUT_ON)

    def test_final_safe_wait_continuation_survives_controller_restart(self):
        with tempfile.TemporaryDirectory() as tempdir:
            session_file = os.path.join(tempdir, "charge_session.json")
            now = 200_000.0
            controller = DiagnosticProductionChargeController(
                DummyHass()
            )
            controller.start("AGM", 90)
            controller.current_stage = controller.STAGE_MIX
            controller._enter_safe_wait_done(
                actions={},
                now=now,
                voltage=16.2,
                current=0.5,
                temp=25.0,
                ah=10.0,
                reason="confirmed_delta_and_sticky_hold",
            )
            with patch("charge_controller.SESSION_FILE", session_file), patch("production_controller.SESSION_FILE", session_file), patch(
                "charge_controller.time.time", return_value=now + 30.0
            ), patch("charge_controller.time.time", return_value=now + 30.0), patch(
                "production_controller.time.time", return_value=now + 30.0
            ):
                controller._save_session(15.0, 0.0, 10.0)
                controller._write_trace_identity_to_session_file()

                restored = DiagnosticProductionChargeController(
                    DummyHass()
                )
                ok, _message = restored.try_restore_session(
                    15.0,
                    0.0,
                    10.0,
                    output_is_on=False,
                    is_cv=False,
                    is_cc=False,
                )

            self.assertTrue(ok)
            self.assertEqual(restored.current_stage, restored.STAGE_SAFE_WAIT)
            self.assertIsInstance(restored._final_safe_wait, FinalSafeWaitContinuation)
            self.assertEqual(
                restored._final_safe_wait.session_id,
                restored._v2_trace_session_id,
            )
            self.assertAlmostEqual(restored._final_safe_wait.started_at, now)


if __name__ == "__main__":
    unittest.main()
