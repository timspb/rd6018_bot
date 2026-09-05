from __future__ import annotations

from typing import Any, Mapping, Optional

from recovery_session import RecoveryTracePoint
from recovery_shadow import ShadowRecoveryRecord, ShadowRecoveryRuntime


COOLING_STAGE_NAMES = frozenset({"cooling", "остывание", "🌡 остывание"})


def _normalized(stage: str) -> str:
    return " ".join(str(stage).strip().lower().replace("_", " ").split())


class CoolingAwareShadowRecoveryRuntime(ShadowRecoveryRuntime):
    """Shadow/evidence runtime where Cooling is a pause, not a chemistry stage.

    Cooling points remain auditable but do not reset Main/Mix signal evidence. On
    resume, active-charge clocks are shifted by the pause duration, continuity-only
    windows are cleared, and partial Delta confirmations are invalidated.
    """

    def observe(
        self,
        point: RecoveryTracePoint,
        *,
        legacy_actions: Optional[Mapping[str, Any]] = None,
        output_is_on: Optional[bool] = True,
    ) -> ShadowRecoveryRecord:
        if _normalized(point.stage) in COOLING_STAGE_NAMES and output_is_on is False:
            analysis = self._neutral_analysis(point)
            decision = self.policy.decide(
                analysis,
                stage=point.stage,
                intent=self.intent,
                output_is_on=output_is_on,
            )
            legacy_effect = self._legacy_effect(legacy_actions)
            record = ShadowRecoveryRecord(
                point=point,
                analysis=analysis,
                decision=decision,
                legacy_effect=legacy_effect,
                disagreement=self._disagreement(decision.decision, legacy_effect),
            )
            self.records.append(record)
            return record
        return super().observe(
            point,
            legacy_actions=legacy_actions,
            output_is_on=output_is_on,
        )

    def resume_after_cooling(self, pause_s: float) -> None:
        pause = max(0.0, float(pause_s))
        tracker = self.tracker
        analyzer = tracker._analyzer

        # Stage/time-to-target clocks count energized chemistry time only.
        if tracker._stage_started_at is not None:
            tracker._stage_started_at += pause

        # Preserve established minima/maxima but freeze their age during OFF.
        if analyzer._current_min_time_s is not None:
            analyzer._current_min_time_s += pause
        if analyzer._voltage_max_time_s is not None:
            analyzer._voltage_max_time_s += pause

        # Rate/plateau windows require continuity and cannot cross an OFF interval.
        analyzer._samples.clear()

        # Partial 1/3 or 2/3 confirmations never survive Cooling. A confirmed Delta
        # is represented by the controller's sticky finish_timer_start and survives.
        analyzer._reversal_confirmations = 0
        analyzer._last_reversal_confirmation_s = None
        analyzer._voltage_reversal_confirmations = 0
        analyzer._last_voltage_reversal_confirmation_s = None
