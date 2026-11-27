"""Fake-only diagnostics for AUTO restore admission and mutation ordering."""
import json
import tempfile
import time
import unittest
from collections import deque
from pathlib import Path

from runtime.charge.persistence import restore_session
from runtime.charge.session_atomic import WriteStatus


class _Host:
    PROFILE_CA = "Ca/Ca"
    STAGE_IDLE = "Idle"
    STAGE_MAIN = "Main Charge"
    STAGE_DONE = "Done"
    STAGE_SAFE_WAIT = "Safe Wait"
    STAGE_DESULFATION = "Desulfation"
    STAGE_MIX = "Mix"

    def __init__(self):
        self.current_stage = self.STAGE_IDLE
        # Grounded restore timeline for terminal-document normalization.
        self.stage_start_time = time.time() - 100.0
        self._stage_tracking_enabled = True
        self._main_current_guard = None
        self._stage_history = deque([{"sentinel": True}], maxlen=8)

    def _clear_session_file(self):
        self.cleared = True

    def _reset_delta_and_blanking(self, _now):
        self.reset_called = True

    def _clear_restored_targets(self):
        self._restored_target_v = None
        self._restored_target_i = None

    def _get_stage_max_hours(self):
        return 1.0

    def _get_target_v_i(self):
        return (14.4, 1.0)

    def _session_rules_summary(self):
        return "fake"

    def _save_session(self, *_args, **_kwargs):
        self.saved = True
        return WriteStatus.COMMITTED, b"preimage"


def _valid_document(**overrides):
    document = {
        "saved_at": time.time(), "profile": "Ca/Ca", "stage": "Main Charge",
        "ah_limit": 60, "target_voltage": 14.4, "target_current": 1.0,
        "safe_wait_target_i": 0.0, "agm_stage_idx": 0,
        "stage_history": [], "start_ah": 0.0, "stage_start_ah": 0.0,
    }
    document.update(overrides)
    return document


class AutoRestoreAtomicAdmissionDiagnostics(unittest.TestCase):
    def invoke(self, document):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "session.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            host = _Host()
            before = dict(host.__dict__)
            try:
                result = restore_session(host, 12.5, 0.0, 0.0, session_file=str(path))
                outcome = ("returned", result)
            except Exception as exc:  # captured to expose direct conversion failures
                outcome = ("raised", type(exc).__name__, str(exc))
            changed = sorted(
                key for key in set(before) | set(host.__dict__)
                if before.get(key, object()) != host.__dict__.get(key, object())
            )
            return outcome, changed

    def test_early_native_recipe_and_retired_rejections_are_mutation_free(self):
        invalid_native = _valid_document(native_recipe_selection_v1={"broken": True})
        retired = _valid_document(
            owner="runtime.charge.persistence", state="retired", schema_version=1,
            stage="RETIRED", retirement_kind="operator_recovery_clearance",
            output_intent="verified_off", verified_off_transaction_id="tx-1",
            verified_off_recorded_utc="2026-11-12T00:00:00Z", session_id="sid",
            battery_id="bid", retired_utc="2026-11-12T00:00:00Z",
        )
        for document in (invalid_native, retired):
            with self.subTest(document=document):
                outcome, changed = self.invoke(document)
                self.assertEqual(outcome[0], "returned")
                self.assertEqual(changed, [])

    def test_invalid_numeric_fields_raise_before_any_host_mutation(self):
        cases = {
            "ah_limit": {"ah_limit": "invalid"},
            "current_retries": {"current_retries": "invalid"},
            "agm_stage_idx": {"agm_stage_idx": "invalid"},
            "safe_wait_target_v": {"safe_wait_target_v": "invalid"},
            "safe_wait_target_i": {"safe_wait_target_i": "invalid"},
            "target_voltage": {"target_voltage": "invalid"},
            "target_current": {"target_current": "invalid"},
            "target_finish_time": {"target_finish_time": "invalid"},
        }
        for label, values in cases.items():
            with self.subTest(field=label):
                outcome, changed = self.invoke(_valid_document(**values))
                self.assertEqual(outcome[0], "raised")
                self.assertEqual(changed, [], f"partial host mutation for {label}")

        # Stage-history shape handling remains the existing persistence owner.
        outcome, changed = self.invoke(_valid_document(stage_history={"bad": "shape"}))
        self.assertEqual(outcome[0], "returned")
        self.assertIn("previous_stage", changed)


if __name__ == "__main__":
    unittest.main()
