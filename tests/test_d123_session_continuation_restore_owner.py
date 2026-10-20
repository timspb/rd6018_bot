import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

from runtime.charge.session_continuation_restore import (
    restore_final_safe_wait,
    restore_recovery_safe_wait,
)
from runtime.charge.strategy.final_safe_wait import FinalSafeWaitContinuation
from runtime.charge.strategy.recovery_safe_wait import RecoverySafeWaitContinuation


class SessionContinuationRestoreOwnerTests(unittest.TestCase):
    def host(self):
        return SimpleNamespace(
            _recovery_safe_wait=None, _final_safe_wait=None,
            current_stage="SAFE_WAIT", STAGE_SAFE_WAIT="SAFE_WAIT",
            STAGE_DESULFATION="DESULFATION", STAGE_MAIN="MAIN",
            STAGE_MIX="MIX", STAGE_DONE="DONE", _safe_wait_next_stage="MAIN",
            _safe_wait_target_v=14.8, _safe_wait_target_i=9.0,
            _safe_wait_start=1000.0, previous_stage="MIX",
            _last_transition_reason="mix_complete", _v2_trace_session_id="sid",
            _v2_trace_started_at=500.0, antisulfate_count=2, _agm_stage_idx=1,
        )

    def test_recovery_and_final_snapshots_restore_typed_identity_bound_values(self):
        host = self.host()
        recovery = RecoverySafeWaitContinuation(
            "DESULFATION", "MAIN", 14.7, 8.0, 900.0, "sid", 2, 1, 500.0,
        ).as_dict()
        final = FinalSafeWaitContinuation(
            "MIX", "DONE", 13.8, 0.7, 950.0, "sid", "mix_complete", 500.0,
        ).as_dict()
        host.current_stage = "SAFE_WAIT"
        restore_recovery_safe_wait(host, {"v2_recovery_safe_wait": recovery})
        restore_final_safe_wait(host, {"v2_final_safe_wait": final})
        self.assertEqual(host._recovery_safe_wait.session_id, "sid")
        self.assertEqual(host._recovery_safe_wait.recovery_attempt, 2)
        self.assertEqual(host._final_safe_wait.completion_reason, "mix_complete")
        self.assertEqual(host._final_safe_wait.session_generation, 500.0)

    def test_stale_identity_rejects_saved_continuation_and_legacy_shapes_migrate(self):
        host = self.host()
        raw = RecoverySafeWaitContinuation(
            "DESULFATION", "MAIN", 14.7, 8.0, 900.0, "other", 2, 1, 500.0,
        ).as_dict()
        restore_recovery_safe_wait(host, {"v2_recovery_safe_wait": raw})
        self.assertIsNone(host._recovery_safe_wait)
        restore_recovery_safe_wait(host, {})
        self.assertIsInstance(host._recovery_safe_wait, RecoverySafeWaitContinuation)
        self.assertEqual(host._recovery_safe_wait.source_stage, "DESULFATION")

    def test_controller_no_longer_owns_restore_bodies(self):
        source = Path("charge_controller.py").read_text()
        tree = ast.parse(source)
        methods = {
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertNotIn("_restore_recovery_safe_wait", methods)
        self.assertNotIn("_restore_final_safe_wait", methods)
        self.assertIn("restore_recovery_safe_wait(self, trace_document)", source)
        self.assertIn("restore_final_safe_wait(self, trace_document)", source)


if __name__ == "__main__":
    unittest.main()
