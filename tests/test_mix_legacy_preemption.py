import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from diagnostic_controller import DiagnosticProductionChargeControllerV2
from mix_active_authority import MixActiveTimeAuthority
from recovery_policy import RecoveryDecision, RecoveryDecisionResult
from signal_analyzer import SignalAnalysis, SignalMetrics, SignalSample


class DummyHass:
    pass


class Clock:
    def __init__(self, value: float):
        self.value = float(value)

    def __call__(self) -> float:
        return self.value


def analysis_at(ts: float, *, voltage: float, current: float) -> SignalAnalysis:
    metrics = SignalMetrics(
        d_voltage_v_per_min=0.0,
        d_current_a_per_min=0.0,
        d_temp_c_per_min=0.0,
        current_min_a=current,
        seconds_since_current_min=0.0,
        delta_current_from_min_a=0.0,
        reversal_threshold_a=max(0.03, current * 0.30),
        current_plateau_span_a=0.0,
        current_plateau_center_a=current,
        reversal_confirmations=0,
        voltage_max_v=None,
        seconds_since_voltage_max=None,
        delta_voltage_from_max_v=None,
        voltage_reversal_threshold_v=None,
        voltage_reversal_confirmations=0,
    )
    return SignalAnalysis(
        sample=SignalSample(ts, voltage, current, 25.0, is_cv=True, is_cc=False),
        metrics=metrics,
        events=frozenset(),
    )


class FixedRuntime:
    def __init__(self):
        self.records = []

    def observe(self, point, *, legacy_actions=None, output_is_on=True):
        analysis = analysis_at(
            point.timestamp_s,
            voltage=point.voltage_v,
            current=point.current_a,
        )
        decision = RecoveryDecisionResult(
            decision=RecoveryDecision.CONTINUE,
            reason="fixed_continue",
            evidence=frozenset(),
        )
        record = SimpleNamespace(
            point=point,
            analysis=analysis,
            decision=decision,
            legacy_effect="continue",
            disagreement=None,
        )
        self.records.append(record)
        return record

    def summary(self):
        return {
            "samples": len(self.records),
            "decision_counts": {},
            "disagreement_counts": {},
        }


class MixLegacyPreemptionTests(unittest.IsolatedAsyncioTestCase):
    def _controller(self, *, now: float, wall_stage_hours: float, active_hours: float, tmp: str):
        controller = DiagnosticProductionChargeControllerV2(
            DummyHass(),
            authoritative=True,
        )
        controller.current_stage = controller.STAGE_MIX
        controller.battery_type = controller.PROFILE_EFB
        controller.ah_capacity = 70
        controller.stage_start_time = now - wall_stage_hours * 3600.0
        controller.total_start_time = now - 30.0 * 3600.0
        controller._v2_target_voltage_v = 16.5
        controller._v2_trace_session_id = "mix-session"
        controller._v2_trace_started_at = now - 30.0 * 3600.0
        controller._stage_start_ah = 10.0
        controller._last_known_output_on = True
        controller._last_log_time = now
        controller._last_hourly_report = now
        controller._blanking_until = 0.0
        controller._delta_monitor_after = 0.0
        controller._v2_runtime = FixedRuntime()

        mono = Clock(100.0)
        wall = Clock(1000.0)
        authority = MixActiveTimeAuthority(
            Path(tmp) / "mix-authority.json",
            monotonic=mono,
            wall_time=wall,
        )
        authority.begin("mix-session", active=True)
        mono.value += active_hours * 3600.0
        wall.value += active_hours * 3600.0
        authority.observe("mix-session", active=False)
        controller._mix_active_authority = authority
        return controller

    async def _tick(self, controller, *, now: float, session_file: str):
        with (
            patch("diagnostic_controller.list_specific_gravity", new=AsyncMock(return_value=[])),
            patch("charge_logic.SESSION_FILE", session_file),
            patch("charge_controller_v2.SESSION_FILE", session_file),
            patch("production_controller.SESSION_FILE", session_file),
            patch("charge_logic.time.time", return_value=now),
            patch("charge_controller_v2.time.time", return_value=now),
            patch("production_controller.time.time", return_value=now),
            patch("auto_strategy_v2.time.time", return_value=now),
        ):
            return await controller.tick(
                16.50,
                0.60,
                25.0,
                True,
                30.0,
                True,
                manual_off_active=False,
                is_cc=False,
            )

    async def test_legacy_efb_20h_wall_timeout_cannot_preempt_v2_24h_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = 500000.0
            controller = self._controller(
                now=now,
                wall_stage_hours=20.5,
                active_hours=20.5,
                tmp=tmp,
            )
            real_stage_start = controller.stage_start_time

            actions = await self._tick(
                controller,
                now=now,
                session_file=str(Path(tmp) / "session.json"),
            )

            self.assertEqual(controller.current_stage, controller.STAGE_MIX)
            self.assertEqual(controller.stage_start_time, real_stage_start)
            self.assertFalse(actions.get("turn_off", False))
            self.assertEqual(
                actions["recovery_shadow"]["authority_decision"]["action"],
                "continue",
            )
            self.assertNotIn("EFB_Mix_limit_20h", str(actions))

    async def test_full_tick_reaches_mix_timeout_instead_of_legacy_safe_wait(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = 600000.0
            controller = self._controller(
                now=now,
                wall_stage_hours=25.0,
                active_hours=24.0,
                tmp=tmp,
            )

            actions = await self._tick(
                controller,
                now=now,
                session_file=str(Path(tmp) / "session.json"),
            )

            self.assertEqual(controller.current_stage, controller.STAGE_DONE)
            self.assertNotEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)
            self.assertTrue(actions.get("turn_off"))
            self.assertEqual(
                actions["recovery_shadow"]["authority_decision"]["action"],
                "stop_and_diagnose",
            )
            self.assertEqual(
                actions["recovery_shadow"]["authority_decision"]["reason"],
                "MIX_TIMEOUT",
            )
            self.assertEqual(controller._mix_active_authority.snapshot.terminal_reason, "MIX_TIMEOUT")
            self.assertNotIn("EFB_Mix_limit_20h", str(actions))


if __name__ == "__main__":
    unittest.main()
