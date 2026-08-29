import unittest
from types import SimpleNamespace
from unittest.mock import patch

from charge_controller_v2 import ChargeControllerV2
from pb_domain import ChargeIntent
from recovery_policy import RecoveryDecision, RecoveryDecisionResult
from signal_analyzer import SignalAnalysis, SignalEvent, SignalMetrics, SignalSample


class DummyHass:
    pass


def analysis_at(
    ts,
    *,
    voltage,
    current,
    is_cv=True,
    is_cc=False,
    current_min=0.2,
    seconds_since_min=0.0,
    events=(),
):
    metrics = SignalMetrics(
        d_voltage_v_per_min=0.0,
        d_current_a_per_min=0.0,
        d_temp_c_per_min=0.0,
        current_min_a=current_min,
        seconds_since_current_min=seconds_since_min,
        delta_current_from_min_a=(current - current_min if current_min is not None else None),
        reversal_threshold_a=(max(0.03, current_min * 0.30) if current_min is not None else None),
        current_plateau_span_a=0.0,
        current_plateau_center_a=current,
        reversal_confirmations=0,
        voltage_max_v=voltage if is_cc else None,
        seconds_since_voltage_max=0.0 if is_cc else None,
        delta_voltage_from_max_v=0.0 if is_cc else None,
        voltage_reversal_threshold_v=0.03 if is_cc else None,
        voltage_reversal_confirmations=0,
    )
    return SignalAnalysis(
        sample=SignalSample(ts, voltage, current, 25.0, is_cv=is_cv, is_cc=is_cc),
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


class ExplodingRuntime:
    records = []

    def observe(self, *args, **kwargs):
        raise RuntimeError("synthetic V2 failure")


class V2ProductionControllerTests(unittest.IsolatedAsyncioTestCase):
    def _controller(self, *, profile="EFB", intent=ChargeIntent.RECOVERY, now=10000.0):
        controller = ChargeControllerV2(DummyHass(), authoritative=True)
        controller.current_stage = controller.STAGE_MAIN
        controller.battery_type = profile
        controller.ah_capacity = 70
        controller.stage_start_time = now - 4 * 3600
        controller.total_start_time = now - 4 * 3600
        controller._v2_target_voltage_v = 14.8 if profile == "EFB" else (15.0 if profile == "AGM" else 14.7)
        controller._v2_intent = intent
        controller._last_known_output_on = True
        return controller

    async def test_normal_tail_completes_without_high_voltage(self):
        now = 10000.0
        controller = self._controller(intent=ChargeIntent.NORMAL, now=now)
        controller._v2_runtime = FixedRuntime(
            analysis_at(now, voltage=14.8, current=0.20, current_min=0.20, seconds_since_min=3 * 3600)
        )
        with patch("charge_logic.time.time", return_value=now), patch("charge_controller_v2.time.time", return_value=now):
            actions = await controller.tick(14.8, 0.20, 25.0, True, 20.0, True, is_cc=False)

        self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)
        self.assertTrue(actions.get("turn_off"))
        self.assertNotEqual(actions.get("set_voltage"), 16.5)
        self.assertEqual(actions["recovery_shadow"]["authority_decision"]["action"], "complete_to_safe_wait")

    async def test_recovery_tail_enters_mix(self):
        now = 20000.0
        controller = self._controller(intent=ChargeIntent.RECOVERY, now=now)
        controller._v2_runtime = FixedRuntime(
            analysis_at(now, voltage=14.8, current=0.20, current_min=0.20, seconds_since_min=3 * 3600)
        )
        with patch("charge_logic.time.time", return_value=now), patch("charge_controller_v2.time.time", return_value=now):
            actions = await controller.tick(14.8, 0.20, 25.0, True, 20.0, True, is_cc=False)

        self.assertEqual(controller.current_stage, controller.STAGE_MIX)
        self.assertAlmostEqual(actions["set_voltage"], 16.5)
        self.assertEqual(actions["recovery_shadow"]["authority_decision"]["action"], "enter_mix")

    async def test_confirmed_recovery_plateau_is_not_blocked_by_c_rate_alone(self):
        now = 30000.0
        controller = self._controller(intent=ChargeIntent.RECOVERY, now=now)
        controller.ah_capacity = 60
        controller._v2_main_plateau_since = now - 40 * 60
        controller._v2_runtime = FixedRuntime(
            analysis_at(
                now,
                voltage=14.8,
                current=1.0,
                current_min=1.0,
                seconds_since_min=40 * 60,
                events={SignalEvent.CURRENT_PLATEAU},
            )
        )
        with patch("charge_logic.time.time", return_value=now), patch("charge_controller_v2.time.time", return_value=now):
            actions = await controller.tick(14.8, 1.0, 25.0, True, 20.0, True, is_cc=False)

        self.assertEqual(controller.current_stage, controller.STAGE_DESULFATION)
        self.assertFalse(actions.get("turn_off", False))
        self.assertAlmostEqual(actions["set_voltage"], 16.3)
        decision = actions["recovery_shadow"]["authority_decision"]
        self.assertEqual(decision["action"], "enter_desulfation")
        self.assertEqual(decision["reason"], "moderate_stable_cv_plateau_recovery_evidence")

    async def test_mix_finish_evidence_starts_sticky_hold_then_completes(self):
        start = 40000.0
        controller = ChargeControllerV2(DummyHass(), authoritative=True)
        controller.current_stage = controller.STAGE_MIX
        controller.battery_type = controller.PROFILE_AGM
        controller.ah_capacity = 70
        controller.stage_start_time = start - 6 * 3600
        controller.total_start_time = start - 10 * 3600
        controller._v2_target_voltage_v = 16.3
        controller._last_known_output_on = True
        controller._v2_runtime = FixedRuntime(
            analysis_at(
                start,
                voltage=16.3,
                current=0.5,
                current_min=0.4,
                seconds_since_min=3600,
                events={SignalEvent.CURRENT_REVERSAL_CONFIRMED, SignalEvent.END_OF_CHARGE_LIKELY},
            ),
            decision=RecoveryDecision.FINISH_STAGE,
        )

        with patch("charge_logic.time.time", return_value=start), patch("charge_controller_v2.time.time", return_value=start):
            actions = await controller.tick(16.3, 0.5, 25.0, True, 30.0, True, is_cc=False)
        self.assertEqual(controller.current_stage, controller.STAGE_MIX)
        self.assertAlmostEqual(controller.finish_timer_start, start)
        self.assertFalse(actions.get("turn_off", False))

        finish = start + 2 * 3600
        controller._v2_runtime = FixedRuntime(
            analysis_at(finish, voltage=16.3, current=0.45, current_min=0.4, seconds_since_min=3 * 3600),
            decision=RecoveryDecision.CONTINUE,
        )
        with patch("charge_logic.time.time", return_value=finish), patch("charge_controller_v2.time.time", return_value=finish):
            actions = await controller.tick(16.3, 0.45, 25.0, True, 31.0, True, is_cc=False)
        self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)
        self.assertTrue(actions.get("turn_off"))

    async def test_mix_cc_finish_uses_voltage_policy(self):
        now = 50000.0
        controller = ChargeControllerV2(DummyHass(), authoritative=True)
        controller.current_stage = controller.STAGE_MIX
        controller.battery_type = controller.PROFILE_EFB
        controller.ah_capacity = 70
        controller.stage_start_time = now - 4 * 3600
        controller._v2_target_voltage_v = 16.5
        controller._last_known_output_on = True
        a = analysis_at(
            now,
            voltage=16.42,
            current=2.1,
            is_cv=False,
            is_cc=True,
            current_min=None,
            events={SignalEvent.VOLTAGE_REVERSAL_CONFIRMED, SignalEvent.END_OF_CHARGE_LIKELY},
        )
        a = SignalAnalysis(
            sample=a.sample,
            metrics=SignalMetrics(
                **{**a.metrics.__dict__, "voltage_max_v": 16.47, "delta_voltage_from_max_v": 0.05}
            ),
            events=a.events,
        )
        controller._v2_runtime = FixedRuntime(a, decision=RecoveryDecision.FINISH_STAGE)
        with patch("charge_logic.time.time", return_value=now), patch("charge_controller_v2.time.time", return_value=now):
            actions = await controller.tick(16.42, 2.1, 25.0, False, 20.0, True, is_cc=True)
        self.assertAlmostEqual(controller.finish_timer_start, now)
        self.assertIn("CC", actions.get("notify", ""))
        self.assertAlmostEqual(controller.v_max_recorded, 16.47)

    async def test_v2_internal_failure_fails_closed_in_authoritative_stage(self):
        now = 60000.0
        controller = self._controller(now=now)
        controller._v2_runtime = ExplodingRuntime()
        with patch("charge_logic.time.time", return_value=now), patch("charge_controller_v2.time.time", return_value=now):
            actions = await controller.tick(14.4, 2.0, 25.0, False, 5.0, True, is_cc=True)
        self.assertEqual(controller.current_stage, controller.STAGE_DONE)
        self.assertTrue(actions.get("turn_off"))
        self.assertEqual(actions["recovery_shadow"]["status"], "error")

    async def test_legacy_main_hard_timeout_remains_active_under_v2_authority(self):
        now = 70000.0
        controller = self._controller(now=now)
        controller.stage_start_time = now - 72 * 3600
        controller.total_start_time = controller.stage_start_time
        controller._v2_runtime = FixedRuntime(analysis_at(now, voltage=14.7, current=0.5))
        with patch("charge_logic.time.time", return_value=now), patch("charge_controller_v2.time.time", return_value=now):
            actions = await controller.tick(14.7, 0.5, 25.0, True, 50.0, True, is_cc=False)
        self.assertEqual(controller.current_stage, controller.STAGE_DONE)
        self.assertTrue(actions.get("turn_off"))
        self.assertIn("ЗАЩИТНЫЙ ЛИМИТ MAIN", actions.get("notify", ""))


if __name__ == "__main__":
    unittest.main()
