import json
import os
import tempfile
import unittest
from unittest.mock import patch

from charge_controller import ManagedChargeController
from runtime.charge.persistence import (
    DONE_COMPLETION_STORAGE,
    DONE_COMPLETION_TERMINAL,
    DONE_OUTPUT_OFF,
    DONE_OUTPUT_ON,
    TerminalPersistenceRequest,
)
from runtime.charge.runtime import stop_diagnose
from tests.d123_final_safe_wait_helpers import enter_final_safe_wait


class Sprint28TerminalPersistenceTests(unittest.TestCase):
    def _storage_controller(self, path):
        controller = ManagedChargeController(object())
        controller.start(ManagedChargeController.PROFILE_AGM, 90)
        controller._v2_trace_session_id = "sprint28-session"
        controller.current_stage = controller.STAGE_MIX
        enter_final_safe_wait(controller, actions={}, now=1000, voltage=16.2,
                              current=0.5, temp=25, ah=10, reason="finish")
        transition = {
            "kind": "final_safe_wait_to_done",
            "session_id": controller._final_safe_wait.session_id,
            "session_generation": controller._final_safe_wait.session_generation,
            "started_at": controller._final_safe_wait.started_at,
        }
        with patch("runtime.charge.persistence.SESSION_FILE", path), \
             patch("charge_controller.SESSION_FILE", path):
            result = controller.commit_verified_enable_transition(
                transition, now=1002, voltage=13.2, current=0, ah=10
            )
        return controller, result

    def test_request_is_typed_and_rejects_unsupported_intent(self):
        req = TerminalPersistenceRequest(
            DONE_COMPLETION_STORAGE, DONE_OUTPUT_ON, 13.2, 0.0, 10.0
        )
        self.assertEqual((req.completion_kind, req.output_intent), ("storage", "on"))
        with self.assertRaises(ValueError):
            TerminalPersistenceRequest("storage", "off", 13.2, 0, 10)

    def test_storage_stage_edge_precedes_one_canonical_save_and_schema_is_shared(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "session.json")
            writer = __import__("runtime.charge.session_atomic", fromlist=["atomic_session_write"]).atomic_session_write
            with patch("runtime.charge.session_atomic.atomic_session_write", wraps=writer) as atomic:
                controller, _ = self._storage_controller(path)
            self.assertEqual(atomic.call_count, 1)
            self.assertEqual(controller.current_stage, controller.STAGE_DONE)
            with open(path, encoding="utf-8") as stream:
                doc = json.load(stream)
            self.assertEqual(doc["completion_kind"], DONE_COMPLETION_STORAGE)
            self.assertEqual(doc["stage"], controller.STAGE_DONE)
            self.assertEqual(doc["output_intent"], DONE_OUTPUT_ON)
            self.assertEqual(doc["terminal_metadata"]["completion_kind"], DONE_COMPLETION_STORAGE)
            self.assertEqual(doc["terminal_metadata"]["output_intent"], DONE_OUTPUT_ON)

    def test_stop_diagnose_uses_shared_terminal_request_after_done_mutation(self):
        controller = ManagedChargeController(object())
        controller.start(ManagedChargeController.PROFILE_EFB, 70)
        controller.current_stage = controller.STAGE_MAIN
        observed = []
        save = controller._save_session

        def record_save(voltage, current, ah, *, terminal_request=None):
            observed.append((controller.current_stage, terminal_request))
            return save(voltage, current, ah, terminal_request=terminal_request)

        controller._save_session = record_save
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "session.json")
            with patch("runtime.charge.persistence.SESSION_FILE", path), \
                 patch("charge_controller.SESSION_FILE", path):
                stop_diagnose.apply_stop_and_diagnose(
                    controller, actions={}, now=1000, voltage=14.8,
                    current=1.2, temp=25, ah=4, reason="diagnose",
                )
            self.assertEqual(len(observed), 1)
            self.assertEqual(observed[0][0], controller.STAGE_DONE)
            req = observed[0][1]
            self.assertEqual((req.completion_kind, req.output_intent),
                             (DONE_COMPLETION_TERMINAL, DONE_OUTPUT_OFF))

    def test_atomic_writer_failure_preserves_both_callers_pre_save_terminal_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "session.json")
            with patch("runtime.charge.persistence.SESSION_FILE", path), \
                 patch("charge_controller.SESSION_FILE", path), \
                 patch("runtime.charge.session_atomic.atomic_session_write", side_effect=OSError("disk full")):
                storage, _ = self._storage_controller(path)
                self.assertEqual(storage.current_stage, storage.STAGE_DONE)
                self.assertEqual(storage._done_completion_kind, DONE_COMPLETION_STORAGE)
                self.assertEqual(storage._done_output_intent, DONE_OUTPUT_ON)

                stop = ManagedChargeController(object())
                stop.start(ManagedChargeController.PROFILE_EFB, 70)
                stop.current_stage = stop.STAGE_MAIN
                stop_diagnose.apply_stop_and_diagnose(
                    stop, actions={}, now=1000, voltage=14.8,
                    current=1.2, temp=25, ah=4, reason="diagnose",
                )
                self.assertEqual(stop.current_stage, stop.STAGE_DONE)
                self.assertEqual(stop._done_completion_kind, DONE_COMPLETION_TERMINAL)
                self.assertEqual(stop._done_output_intent, DONE_OUTPUT_OFF)


if __name__ == "__main__":
    unittest.main()
