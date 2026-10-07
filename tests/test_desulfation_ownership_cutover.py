import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from charge_controller import (
    INTERMEDIATE_RECOVERY_DURATION_SEC,
    RecoverySafeWaitContinuation,
)
from pb_domain import ChargeIntent
from production_controller import ProductionChargeController
from recovery_policy import RecoveryDecision, RecoveryDecisionResult
from signal_analyzer import SignalAnalysis, SignalEvent, SignalMetrics, SignalSample


class DummyHass:
    pass


def analysis_at(
    ts: float,
    *,
    voltage: float,
    current: float,
    current_min: float = 0.20,
    seconds_since_min: float = 0.0,
    events=(),
):
    metrics = SignalMetrics(
        d_voltage_v_per_min=0.0,
        d_current_a_per_min=0.0,
        d_temp_c_per_min=0.0,
        current_min_a=current_min,
        seconds_since_current_min=seconds_since_min,
        delta_current_from_min_a=current - current_min,
        reversal_threshold_a=max(0.03, current_min * 0.30),
        current_plateau_span_a=0.0,
        current_plateau_center_a=current,
        reversal_confirmations=3 if SignalEvent.CURRENT_REVERSAL_CONFIRMED in events else 0,
        voltage_max_v=None,
        seconds_since_voltage_max=None,
        delta_voltage_from_max_v=None,
        voltage_reversal_threshold_v=None,
        voltage_reversal_confirmations=0,
    )
    return SignalAnalysis(
        sample=SignalSample(ts, voltage, current, 25.0, is_cv=True, is_cc=False),
        metrics=metrics,
        events=frozenset(events),
    )


class FixedRuntime:
    def __init__(self, analysis, decision=RecoveryDecision.CONTINUE):
        self.analysis = analysis
        self.decision = decision
        self.records = []

    def observe(self, point, *, legacy_actions=None, output_is_on=True):
        result = RecoveryDecisionResult(
            decision=self.decision,
            reason=f"fixed_{self.decision.value}",
            evidence=self.analysis.events,
        )
        record = SimpleNamespace(
            point=point,
            analysis=self.analysis,
            decision=result,
            legacy_effect="continue",
            disagreement=None,
        )
        self.records.append(record)
        return record

    def summary(self):
        return {"samples": len(self.records), "decision_counts": {}, "disagreement_counts": {}}


class DesulfationOwnershipCutoverTests(unittest.IsolatedAsyncioTestCase):
    def _controller(self, *, profile="AGM", capacity=90, now=10_000.0):
        controller = ProductionChargeController(DummyHass(), authoritative=True)
        controller.battery_type = profile
        controller.ah_capacity = capacity
        controller.current_stage = controller.STAGE_DESULFATION
        controller.stage_start_time = now
        controller.total_start_time = now - 4 * 3600
        controller._stage_start_ah = 10.0
        controller._agm_stage_idx = 2 if profile == "AGM" else 0
        controller.antisulfate_count = 2
        controller._v2_trace_session_id = "session-cutover"
        controller._v2_trace_started_at = now - 4 * 3600
        controller._v2_intent = ChargeIntent.RECOVERY
        controller._v2_target_voltage_v = controller._desulf_target(25.0)[0]
        controller._last_known_output_on = True
        controller._v2_runtime = FixedRuntime(
            analysis_at(now, voltage=16.3, current=0.5)
        )
        return controller

    async def _tick(self, controller, *, now, voltage=16.3, current=0.5, temp=25.0, output=True):
        controller._v2_runtime = FixedRuntime(
            analysis_at(now, voltage=voltage, current=current)
        )
        with patch("charge_logic.time.time", return_value=now), patch(
            "charge_controller.time.time", return_value=now
        ), patch("production_controller.time.time", return_value=now):
            return await controller.tick(
                voltage=voltage,
                current=current,
                temp_ext=temp,
                is_cv=True,
                ah=12.0,
                output_is_on=output,
                is_cc=False,
            )

    def _commit_verified_resume(self, controller, actions, *, now, voltage=14.3, current=0.0, ah=12.0):
        transition = actions.get("verified_enable_transition")
        self.assertIsInstance(transition, dict)
        return controller.commit_verified_enable_transition(
            transition,
            now=now,
            voltage=voltage,
            current=current,
            ah=ah,
        )

    async def test_desulfation_waits_until_exact_bounded_duration_and_turns_off_once(self):
        start = 10_000.0
        controller = self._controller(now=start)

        actions = await self._tick(
            controller,
            now=start + INTERMEDIATE_RECOVERY_DURATION_SEC - 1.0,
        )
        self.assertEqual(controller.current_stage, controller.STAGE_DESULFATION)
        self.assertNotIn("turn_off", actions)
        self.assertIsNone(controller._recovery_safe_wait)

        actions = await self._tick(
            controller,
            now=start + INTERMEDIATE_RECOVERY_DURATION_SEC,
        )
        self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)
        self.assertTrue(actions.get("turn_off"))
        self.assertNotIn("turn_on", actions)
        continuation = controller._recovery_safe_wait
        self.assertIsInstance(continuation, RecoverySafeWaitContinuation)
        self.assertEqual(continuation.source_stage, controller.STAGE_DESULFATION)
        self.assertEqual(continuation.next_stage, controller.STAGE_MAIN)
        self.assertEqual(continuation.session_id, "session-cutover")
        self.assertEqual(continuation.recovery_attempt, 2)
        self.assertEqual(continuation.agm_stage_idx, 2)
        self.assertAlmostEqual(continuation.target_voltage_v, 14.8)
        self.assertAlmostEqual(continuation.target_current_a, 9.0)

        # The OFF intent belongs to the DESULFATION->SAFE_WAIT edge only; while the
        # relaxation continues the controller neither repeats OFF nor re-enables.
        actions = await self._tick(
            controller,
            now=start + INTERMEDIATE_RECOVERY_DURATION_SEC + 60.0,
            voltage=15.0,
            current=0.0,
            output=False,
        )
        self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)
        self.assertNotIn("turn_off", actions)
        self.assertNotIn("turn_on", actions)

    async def test_imin_or_delta_evidence_cannot_finish_intermediate_recovery(self):
        start = 20_000.0
        now = start + 3600.0
        controller = self._controller(now=start)
        controller._v2_runtime = FixedRuntime(
            analysis_at(
                now,
                voltage=16.3,
                current=0.45,
                current_min=0.20,
                seconds_since_min=1800.0,
                events={
                    SignalEvent.CURRENT_REVERSAL_CONFIRMED,
                    SignalEvent.END_OF_CHARGE_LIKELY,
                },
            ),
            decision=RecoveryDecision.FINISH_STAGE,
        )
        with patch("charge_logic.time.time", return_value=now), patch(
            "charge_controller.time.time", return_value=now
        ), patch("production_controller.time.time", return_value=now):
            actions = await controller.tick(
                16.3,
                0.45,
                25.0,
                True,
                12.0,
                True,
                is_cc=False,
            )
        self.assertEqual(controller.current_stage, controller.STAGE_DESULFATION)
        self.assertNotIn("turn_off", actions)
        self.assertIsNone(controller._recovery_safe_wait)

    async def test_recovery_safe_wait_threshold_returns_exact_agm_step(self):
        start = 30_000.0
        controller = self._controller(now=start)
        await self._tick(controller, now=start + INTERMEDIATE_RECOVERY_DURATION_SEC)
        attempt = controller.antisulfate_count
        agm_step = controller._agm_stage_idx
        continuation = controller._recovery_safe_wait
        self.assertIsNotNone(continuation)

        actions = await self._tick(
            controller,
            now=start + INTERMEDIATE_RECOVERY_DURATION_SEC + 300.0,
            voltage=continuation.target_voltage_v - 0.5,
            current=0.0,
            output=False,
        )
        self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)
        self.assertTrue(actions.get("turn_on"))
        self.assertAlmostEqual(actions["set_voltage"], 14.8)
        self.assertAlmostEqual(actions["set_current"], 9.0)
        self.assertEqual(controller.antisulfate_count, attempt)
        self.assertEqual(controller._agm_stage_idx, agm_step)
        self.assertIsNotNone(controller._recovery_safe_wait)
        committed = self._commit_verified_resume(
            controller,
            actions,
            now=start + INTERMEDIATE_RECOVERY_DURATION_SEC + 301.0,
            voltage=continuation.target_voltage_v - 0.5,
        )
        self.assertIsInstance(committed, dict)
        self.assertEqual(controller.current_stage, controller.STAGE_MAIN)
        self.assertIsNone(controller._recovery_safe_wait)

    async def test_recovery_safe_wait_requires_confirmed_output_off_before_return(self):
        start = 35_000.0
        controller = self._controller(now=start)
        await self._tick(controller, now=start + INTERMEDIATE_RECOVERY_DURATION_SEC)
        continuation = controller._recovery_safe_wait
        self.assertIsNotNone(continuation)

        # Even with voltage already below the relaxation threshold, an ON/unknown
        # physical Output must never grant automatic re-enable/return authority.
        actions = await self._tick(
            controller,
            now=continuation.started_at + 300.0,
            voltage=continuation.target_voltage_v - 0.6,
            current=0.0,
            output=True,
        )
        self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)
        self.assertNotIn("turn_on", actions)
        self.assertIsNotNone(controller._recovery_safe_wait)

    async def test_pending_verified_resume_does_not_request_duplicate_enable_when_output_is_on(self):
        start = 37_000.0
        controller = self._controller(now=start)
        await self._tick(controller, now=start + INTERMEDIATE_RECOVERY_DURATION_SEC)
        continuation = controller._recovery_safe_wait
        self.assertIsNotNone(continuation)

        first = await self._tick(
            controller,
            now=continuation.started_at + 300.0,
            voltage=continuation.target_voltage_v - 0.6,
            current=0.0,
            output=False,
        )
        self.assertTrue(first.get("turn_on"))
        self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)

        # Before the verified transaction is committed, a fresh physical ON
        # observation suppresses another enable request. The stage remains pending.
        second = await self._tick(
            controller,
            now=continuation.started_at + 301.0,
            voltage=continuation.target_voltage_v - 0.6,
            current=0.0,
            output=True,
        )
        self.assertNotIn("turn_on", second)
        self.assertNotIn("verified_enable_transition", second)
        self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)
        self.assertIsNotNone(controller._recovery_safe_wait)

    async def test_recovery_safe_wait_bounded_timeout_returns_main(self):
        start = 40_000.0
        controller = self._controller(now=start)
        await self._tick(controller, now=start + INTERMEDIATE_RECOVERY_DURATION_SEC)
        continuation = controller._recovery_safe_wait
        self.assertIsNotNone(continuation)
        now = continuation.started_at + 2 * 3600
        actions = await self._tick(
            controller,
            now=now,
            voltage=continuation.target_voltage_v,
            current=0.0,
            output=False,
        )
        self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)
        self.assertTrue(actions.get("turn_on"))
        self.assertIn("RECOVERY_SAFE_WAIT_ENABLE_ATTEMPT", actions.get("log_event", ""))
        self.assertEqual(actions["verified_enable_transition"]["reason"], "timeout")
        committed = self._commit_verified_resume(
            controller,
            actions,
            now=now + 1.0,
            voltage=continuation.target_voltage_v,
        )
        self.assertIsInstance(committed, dict)
        self.assertIn("TIMEOUT", committed.get("log_event", ""))
        self.assertEqual(controller.current_stage, controller.STAGE_MAIN)

    async def test_recovery_safe_wait_does_not_commit_without_matching_verified_token(self):
        start = 45_000.0
        controller = self._controller(now=start)
        await self._tick(controller, now=start + INTERMEDIATE_RECOVERY_DURATION_SEC)
        continuation = controller._recovery_safe_wait
        actions = await self._tick(
            controller,
            now=continuation.started_at + 300.0,
            voltage=continuation.target_voltage_v - 0.6,
            current=0.0,
            output=False,
        )
        bad = dict(actions["verified_enable_transition"])
        bad["session_id"] = "stale-session"
        committed = controller.commit_verified_enable_transition(
            bad,
            now=continuation.started_at + 301.0,
            voltage=continuation.target_voltage_v - 0.6,
            current=0.0,
            ah=12.0,
        )
        self.assertIsNone(committed)
        self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)
        self.assertIsNotNone(controller._recovery_safe_wait)

    async def test_recovery_cutover_uses_profile_main_target_for_all_pb_chemistries(self):
        cases = (
            ("AGM", 90, 2, 14.8, 9.0),
            ("EFB", 70, 0, 14.8, 7.0),
            ("Ca/Ca", 60, 0, 14.7, 6.0),
        )
        for index, (profile, capacity, agm_step, expected_v, expected_i) in enumerate(cases):
            with self.subTest(profile=profile):
                start = 50_000.0 + index * 20_000.0
                controller = self._controller(profile=profile, capacity=capacity, now=start)
                controller._agm_stage_idx = agm_step
                actions = await self._tick(
                    controller,
                    now=start + INTERMEDIATE_RECOVERY_DURATION_SEC,
                    voltage=16.3 if profile == "AGM" else 16.5,
                    current=1.0,
                )
                self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)
                self.assertTrue(actions.get("turn_off"))
                continuation = controller._recovery_safe_wait
                self.assertAlmostEqual(continuation.target_voltage_v, expected_v)
                self.assertAlmostEqual(continuation.target_current_a, expected_i)

    async def test_cooling_freezes_desulfation_clock(self):
        start = 100_000.0
        controller = self._controller(now=start)
        # One active hour, then Cooling.
        actions = await self._tick(
            controller,
            now=start + 3600.0,
            temp=40.0,
            output=True,
        )
        self.assertEqual(controller.current_stage, controller.STAGE_COOLING)
        self.assertTrue(actions.get("turn_off"))

        # Spend a full hour cooling. Resume must move the source stage clock forward
        # by that hour, so active recovery age remains exactly one hour.
        resume_at = start + 7200.0
        actions = await self._tick(
            controller,
            now=resume_at,
            voltage=15.0,
            current=0.0,
            temp=35.0,
            output=False,
        )
        self.assertEqual(controller.current_stage, controller.STAGE_DESULFATION)
        self.assertAlmostEqual(resume_at - controller.stage_start_time, 3600.0)
        self.assertTrue(actions.get("turn_on"))

        # Another 3599 s active is still below the 2h budget.
        actions = await self._tick(
            controller,
            now=resume_at + 3599.0,
            voltage=16.3,
            current=0.5,
            temp=25.0,
            output=True,
        )
        self.assertEqual(controller.current_stage, controller.STAGE_DESULFATION)
        self.assertNotIn("turn_off", actions)

        # Exactly one more second reaches two active hours.
        actions = await self._tick(
            controller,
            now=resume_at + 3600.0,
            voltage=16.3,
            current=0.5,
            temp=25.0,
            output=True,
        )
        self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)
        self.assertTrue(actions.get("turn_off"))

    def test_recovery_safe_wait_typed_continuation_survives_restart(self):
        with tempfile.TemporaryDirectory() as tempdir:
            session_file = os.path.join(tempdir, "charge_session.json")
            now = 200_000.0
            controller = self._controller(now=now - 3 * 3600)
            controller.current_stage = controller.STAGE_SAFE_WAIT
            controller.stage_start_time = now - 600.0
            controller._safe_wait_start = now - 600.0
            controller._safe_wait_next_stage = controller.STAGE_MAIN
            controller._safe_wait_target_v = 14.8
            controller._safe_wait_target_i = 9.0
            controller._recovery_safe_wait = RecoverySafeWaitContinuation(
                source_stage=controller.STAGE_DESULFATION,
                next_stage=controller.STAGE_MAIN,
                target_voltage_v=14.8,
                target_current_a=9.0,
                started_at=now - 600.0,
                session_id=controller._v2_trace_session_id,
                recovery_attempt=controller.antisulfate_count,
                agm_stage_idx=controller._agm_stage_idx,
                session_generation=controller._v2_trace_started_at,
            )
            with patch("charge_logic.SESSION_FILE", session_file), patch(
                "charge_controller.SESSION_FILE", session_file
            ), patch("production_controller.SESSION_FILE", session_file), patch(
                "charge_logic.time.time", return_value=now
            ), patch("charge_controller.time.time", return_value=now), patch(
                "production_controller.time.time", return_value=now
            ):
                controller._save_session(15.0, 0.0, 12.0)
                with open(session_file, "r", encoding="utf-8") as handle:
                    saved = json.load(handle)
                self.assertEqual(saved["v2_recovery_safe_wait"]["source_stage"], controller.STAGE_DESULFATION)

                restored = ProductionChargeController(DummyHass(), authoritative=True)
                ok, _ = restored.try_restore_session(
                    15.0,
                    0.0,
                    12.0,
                    output_is_on=False,
                    is_cv=False,
                    is_cc=False,
                )

            self.assertTrue(ok)
            self.assertEqual(restored.current_stage, restored.STAGE_SAFE_WAIT)
            self.assertIsInstance(restored._recovery_safe_wait, RecoverySafeWaitContinuation)
            self.assertEqual(restored._recovery_safe_wait.session_id, restored._v2_trace_session_id)
            self.assertAlmostEqual(
                restored._recovery_safe_wait.session_generation,
                restored._v2_trace_started_at,
            )
            self.assertEqual(restored._recovery_safe_wait.recovery_attempt, 2)
            self.assertEqual(restored._recovery_safe_wait.agm_stage_idx, 2)
            self.assertAlmostEqual(restored._recovery_safe_wait.started_at, now - 600.0)


if __name__ == "__main__":
    unittest.main()
