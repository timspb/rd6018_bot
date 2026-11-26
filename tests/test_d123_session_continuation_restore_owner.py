import ast
import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from runtime.charge.session_continuation_restore import (
    restore_controller_session,
    restore_desulfation_stage_clock,
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

    def test_desulfation_clock_restores_only_finite_fresh_persisted_time(self):
        host = self.host()
        host.current_stage = "DESULFATION"
        now = 200_000.0
        accepted = (now, now - 86_400.0)
        for saved in accepted:
            with self.subTest(saved=saved):
                host.stage_start_time = -1.0
                with patch("runtime.charge.session_continuation_restore.time.time", return_value=now):
                    restore_desulfation_stage_clock(
                        host, {"stage_start_time": saved}, max_session_age_s=86_400.0,
                    )
                self.assertEqual(host.stage_start_time, saved)

        rejected = (0, -1, now + 1, now - 86_400.1, "bad", float("nan"), float("inf"))
        for saved in rejected:
            with self.subTest(saved=saved):
                host.stage_start_time = 123.0
                with patch("runtime.charge.session_continuation_restore.time.time", return_value=now):
                    restore_desulfation_stage_clock(
                        host, {"stage_start_time": saved}, max_session_age_s=86_400.0,
                    )
                self.assertEqual(host.stage_start_time, 123.0)

    def test_desulfation_clock_does_not_override_other_stages(self):
        host = self.host()
        host.current_stage = "MAIN"
        host.stage_start_time = 123.0
        with patch("runtime.charge.session_continuation_restore.time.time", return_value=50_000.0):
            restore_desulfation_stage_clock(
                host, {"stage_start_time": 49_999.0}, max_session_age_s=86_400.0,
            )
        self.assertEqual(host.stage_start_time, 123.0)

    def test_controller_restore_owner_preserves_rejection_and_guarded_activation(self):
        host = SimpleNamespace(
            battery_type="CUSTOM", PROFILE_CUSTOM="CUSTOM", stop_calls=[],
            _recovery_safe_wait=object(), _final_safe_wait=object(),
            _v2_runtime=object(), _guarded_restore_candidate=object(),
            _guarded_restore_activated_off=False,
        )
        host.stop = lambda **kwargs: host.stop_calls.append(kwargs)
        restored = restore_controller_session(
            host, 12.0, 0.0, 0.0, output_is_on=True, is_cv=False, is_cc=False,
            guarded_activation_permit=None, session_file="session.json",
            persist_restore=lambda *_args, **_kwargs: (True, "restored"),
            enrich_restored_session=lambda *_args, **_kwargs: True,
            custom_profile="CUSTOM", max_session_age_s=86_400.0,
        )
        self.assertEqual(restored, (
            False,
            "Historical Custom session is retired; restart Manual with operator authorization.",
        ))
        self.assertEqual(host.stop_calls, [{"clear_session": True}])
        self.assertIsNone(host._recovery_safe_wait)
        self.assertIsNone(host._final_safe_wait)
        self.assertIsNone(host._v2_runtime)

        host.battery_type = "AGM"
        host._guarded_restore_candidate = object()
        host._guarded_restore_activated_off = False
        with patch(
            "runtime.charge.session_continuation_restore.finish_session_restore",
            return_value=(True, "restored"),
        ) as finish:
            restored = restore_controller_session(
                host, 12.0, 0.0, 0.0, output_is_on=False, is_cv=False, is_cc=False,
                guarded_activation_permit=object(), session_file="session.json",
                persist_restore=lambda *_args, **_kwargs: (True, "restored"),
                enrich_restored_session=lambda *_args, **_kwargs: True,
                custom_profile="CUSTOM", max_session_age_s=86_400.0,
            )
        self.assertEqual(restored, (True, "restored"))
        self.assertIsNone(host._guarded_restore_candidate)
        self.assertTrue(host._guarded_restore_activated_off)
        self.assertTrue(finish.call_args.kwargs["guarded_activation"])

    def test_controller_restore_owner_propagates_cancel_after_partial_persistence_mutation(self):
        host = SimpleNamespace(battery_type="AGM", partial_restore=None)

        def cancel_after_mutation(*_args, **_kwargs):
            host.partial_restore = "persisted stage applied"
            raise asyncio.CancelledError()

        with self.assertRaises(asyncio.CancelledError):
            restore_controller_session(
                host, 12.0, 0.0, 0.0, output_is_on=False, is_cv=False, is_cc=False,
                guarded_activation_permit=object(), session_file="session.json",
                persist_restore=cancel_after_mutation,
                enrich_restored_session=lambda *_args, **_kwargs: True,
                custom_profile="CUSTOM", max_session_age_s=86_400.0,
            )
        self.assertEqual(host.partial_restore, "persisted stage applied")

    def test_controller_restore_owner_keeps_guarded_candidate_when_continuation_raises(self):
        host = SimpleNamespace(
            battery_type="AGM", _guarded_restore_candidate="candidate",
            _guarded_restore_activated_off=False,
        )
        with patch(
            "runtime.charge.session_continuation_restore.finish_session_restore",
            side_effect=RuntimeError("terminal persistence failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "terminal persistence failed"):
                restore_controller_session(
                    host, 12.0, 0.0, 0.0, output_is_on=False, is_cv=False, is_cc=False,
                    guarded_activation_permit=object(), session_file="session.json",
                    persist_restore=lambda *_args, **_kwargs: (True, "restored"),
                    enrich_restored_session=lambda *_args, **_kwargs: True,
                    custom_profile="CUSTOM", max_session_age_s=86_400.0,
                )
        self.assertEqual(host._guarded_restore_candidate, "candidate")
        self.assertFalse(host._guarded_restore_activated_off)

    def test_controller_no_longer_owns_restore_bodies(self):
        source = Path("charge_controller.py").read_text()
        tree = ast.parse(source)
        methods = {
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertNotIn("_restore_recovery_safe_wait", methods)
        self.assertNotIn("_restore_final_safe_wait", methods)
        controller_clock = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "_restore_desulfation_stage_clock"
        )
        calls = [
            node for node in ast.walk(controller_clock)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "restore_desulfation_stage_clock"
        ]
        self.assertEqual(len(calls), 1)
        self.assertFalse(any(isinstance(node, (ast.If, ast.Try, ast.Assign)) for node in controller_clock.body))
        owner = Path("runtime/charge/session_continuation_restore.py").read_text()
        self.assertIn("def restore_desulfation_stage_clock(", owner)
        self.assertIn("restore_recovery_safe_wait(host, document)", owner)
        self.assertIn("restore_final_safe_wait(host, document)", owner)
        self.assertIn("restore_controller_session(", source)
        self.assertIn("finish_session_restore(", owner)


if __name__ == "__main__":
    unittest.main()
