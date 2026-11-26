"""Fake-only contracts for AUTO restore scalar projection and apply parity."""

import json
import tempfile
import time
import unittest
from collections import deque
from pathlib import Path

from runtime.charge.persistence import restore_session
from runtime.charge.restore_projection import project_restore_scalars
from runtime.charge.session_atomic import WriteStatus
from runtime.safety.voltage_variables import clamp_pb_automatic_target_voltage


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


def _document(**overrides):
    result = {
        "saved_at": time.time(), "profile": "Ca/Ca", "stage": "Main Charge",
        "ah_limit": 60, "current_retries": 2, "agm_stage_idx": 99,
        "start_ah": 1.25, "stage_start_ah": 2.5,
        "stage_start_voltage": "bad", "stage_start_current": None,
        "stage_start_temp": "bad", "safe_wait_target_v": 13.2,
        "safe_wait_target_i": 0.5, "target_voltage": 14.7,
        "target_current": 99.0, "stage_history": [],
    }
    result.update(overrides)
    return result


class AutoRestoreProjectionTests(unittest.TestCase):
    def test_projection_preserves_defaults_clamps_and_legacy_fallbacks(self):
        projection = project_restore_scalars(
            _document(), ah=4.0, voltage=12.4, current=0.3,
            agm_stage_count=4, max_stage_current=10.0,
            clamp_voltage=clamp_pb_automatic_target_voltage,
        )
        self.assertEqual(projection.ah_limit, 60)
        self.assertEqual(projection.current_retries, 2)
        self.assertEqual(projection.agm_stage_idx, 3)
        self.assertEqual(projection.start_ah, 1.25)
        self.assertEqual(projection.stage_start_ah, 2.5)
        self.assertEqual(projection.stage_start_voltage, 12.4)
        self.assertEqual(projection.stage_start_current, 0.3)
        self.assertEqual(projection.stage_start_temp, 0.0)
        self.assertEqual(projection.safe_wait_target_v, 13.2)
        self.assertEqual(projection.safe_wait_target_i, 0.5)
        self.assertEqual(projection.target_current, 10.0)
        self.assertEqual(
            projection.target_voltage,
            clamp_pb_automatic_target_voltage(14.7),
        )

    def test_accepted_restore_applies_projected_values_and_keeps_done_off(self):
        document = _document(
            stage="Done", target_voltage=14.4, target_current=2.0,
            current_retries=4, agm_stage_idx=2, target_finish_time=None,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "session.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            host = _Host()
            result = restore_session(host, 12.4, 0.3, 4.0, session_file=str(path))
        self.assertTrue(result[0])
        self.assertEqual(host.ah_capacity, 60)
        self.assertEqual(host.antisulfate_count, 4)
        self.assertEqual(host._agm_stage_idx, 2)
        self.assertEqual(host._start_ah, 1.25)
        self.assertEqual(host._stage_start_ah, 2.5)
        self.assertEqual(host._stage_start_voltage, 12.4)
        self.assertEqual(host._stage_start_current, 0.3)
        self.assertEqual(host._stage_start_temp, 0.0)
        self.assertEqual(host._done_output_intent, "off")
        self.assertFalse(getattr(host, "output_on", False))

    def test_guard_candidate_still_precedes_projection_and_preserves_hold(self):
        from runtime.charge.session import GuardedRestoreCandidate
        from runtime.charge.strategy.main_current_guard import MainCurrentGuard
        from runtime.charge.strategy.main_guard_session import attach_guard

        document = _document(
            profile="EFB", v2_trace_session_id="sid", v2_battery_id="battery",
            ah_limit=60, agm_stage_idx="invalid",
        )
        guard = MainCurrentGuard.start(
            session_id="sid", battery_id="battery", segment_id="main",
            capacity_ah=60, recipe_initial_current_a=6,
        )
        document = attach_guard(document, guard, now_s=time.time(), expected_revision=0)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "session.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            host = _Host()
            before = dict(host.__dict__)
            result = restore_session(host, 12.4, 0.3, 4.0, session_file=str(path))
        self.assertFalse(result[0])
        self.assertIsInstance(host._guarded_restore_candidate, GuardedRestoreCandidate)
        self.assertEqual(
            {key: value for key, value in host.__dict__.items() if key != "_guarded_restore_candidate"},
            before,
        )


if __name__ == "__main__":
    unittest.main()
