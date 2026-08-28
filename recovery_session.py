from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Mapping, Optional

from battery_registry import RecoveryCycleEvidence
from pb_domain import BatteryCondition, ChargeIntent
from signal_analyzer import SignalAnalysis, SignalAnalyzer, SignalEvent, SignalSample


MAIN_STAGE_NAMES = frozenset({"main", "main charge", "bulk", "absorption"})
HV_STAGE_NAMES = frozenset({"mix", "mix mode", "desulfation", "десульфатация", "conditioning", "recovery"})
RELAX_STAGE_NAMES = frozenset({"relax", "safe_wait", "безопасное ожидание", "rest"})


@dataclass(frozen=True)
class RecoveryTracePoint:
    timestamp_s: float
    stage: str
    voltage_v: float
    current_a: float
    temp_c: float
    is_cv: bool = False
    target_voltage_v: Optional[float] = None
    ah: Optional[float] = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "RecoveryTracePoint":
        return cls(
            timestamp_s=float(raw["timestamp_s"]),
            stage=str(raw["stage"]),
            voltage_v=float(raw["voltage_v"]),
            current_a=float(raw["current_a"]),
            temp_c=float(raw["temp_c"]),
            is_cv=bool(raw.get("is_cv", False)),
            target_voltage_v=(
                float(raw["target_voltage_v"])
                if raw.get("target_voltage_v") is not None
                else None
            ),
            ah=float(raw["ah"]) if raw.get("ah") is not None else None,
        )


class RecoverySessionTracker:
    """Aggregate deterministic recovery evidence from one U/I/T telemetry stream.

    This class records evidence only. It never selects a recipe or voltage and never
    declares the battery healthy from a low Imin alone.
    """

    def __init__(
        self,
        *,
        battery_id: str,
        started_at: float,
        intent: ChargeIntent,
        condition_before: BatteryCondition = BatteryCondition.UNKNOWN,
        target_tolerance_v: float = 0.20,
    ) -> None:
        self.evidence = RecoveryCycleEvidence(
            battery_id=battery_id,
            started_at=float(started_at),
            intent=intent,
            condition_before=condition_before,
        )
        self.target_tolerance_v = float(target_tolerance_v)
        self._stage_key: Optional[str] = None
        self._stage_started_at: Optional[float] = None
        self._stage_start_ah: Optional[float] = None
        self._analyzer = SignalAnalyzer()
        self._relax_started_at: Optional[float] = None

    @staticmethod
    def _normalize_stage(stage: str) -> str:
        return " ".join(str(stage).strip().lower().replace("_", " ").split())

    @classmethod
    def _stage_kind(cls, stage: str) -> str:
        key = cls._normalize_stage(stage)
        if key in MAIN_STAGE_NAMES:
            return "main"
        if key in HV_STAGE_NAMES:
            return "hv"
        if key in RELAX_STAGE_NAMES:
            return "relax"
        return "other"

    def _enter_stage(self, point: RecoveryTracePoint) -> None:
        key = self._normalize_stage(point.stage)
        self._stage_key = key
        self._stage_started_at = point.timestamp_s
        self._stage_start_ah = point.ah
        self._analyzer.reset_stage(key, target_voltage_v=point.target_voltage_v)
        if self._stage_kind(point.stage) == "relax" and self._relax_started_at is None:
            self._relax_started_at = point.timestamp_s

    def _update_temperature(self, point: RecoveryTracePoint, analysis: SignalAnalysis) -> None:
        temp_start = self.evidence.temp_start_c
        if temp_start is None:
            temp_start = point.temp_c
        temp_max = self.evidence.temp_max_c
        if temp_max is None or point.temp_c > temp_max:
            temp_max = point.temp_c
        max_rate = self.evidence.max_dtemp_c_per_min
        current_rate = analysis.metrics.d_temp_c_per_min
        if current_rate is not None and (max_rate is None or current_rate > max_rate):
            max_rate = current_rate
        self.evidence = replace(
            self.evidence,
            temp_start_c=temp_start,
            temp_max_c=temp_max,
            max_dtemp_c_per_min=max_rate,
        )

    def _update_charge_stage(self, point: RecoveryTracePoint, analysis: SignalAnalysis) -> None:
        kind = self._stage_kind(point.stage)
        if kind not in {"main", "hv"}:
            return

        target = point.target_voltage_v
        time_to_target: Optional[float] = None
        if target is not None and self._stage_started_at is not None:
            reached = point.voltage_v >= target - self.target_tolerance_v
            if reached:
                current = (
                    self.evidence.main_time_to_target_s
                    if kind == "main"
                    else self.evidence.hv_time_to_target_s
                )
                if current is None:
                    time_to_target = point.timestamp_s - self._stage_started_at

        imin = analysis.metrics.current_min_a
        if kind == "main":
            kwargs = {
                "main_target_v": target if target is not None else self.evidence.main_target_v,
                "main_imin_a": imin if imin is not None else self.evidence.main_imin_a,
            }
            if time_to_target is not None:
                kwargs["main_time_to_target_s"] = time_to_target
            if point.ah is not None and self._stage_start_ah is not None:
                kwargs["main_ah_in"] = max(0.0, point.ah - self._stage_start_ah)
            self.evidence = replace(self.evidence, **kwargs)
            return

        kwargs = {
            "hv_target_v": target if target is not None else self.evidence.hv_target_v,
            "hv_imin_a": imin if imin is not None else self.evidence.hv_imin_a,
        }
        if time_to_target is not None:
            kwargs["hv_time_to_target_s"] = time_to_target
        if analysis.has(SignalEvent.CURRENT_REVERSAL_CONFIRMED):
            delta = analysis.metrics.delta_current_from_min_a
            if delta is not None:
                kwargs["hv_reversal_delta_a"] = delta
        self.evidence = replace(self.evidence, **kwargs)

    def _update_relaxation(self, point: RecoveryTracePoint) -> None:
        if self._stage_kind(point.stage) != "relax":
            return
        if self._relax_started_at is None:
            self._relax_started_at = point.timestamp_s
        elapsed = point.timestamp_s - self._relax_started_at
        windows = (
            (5 * 60, "relax_v_5m"),
            (15 * 60, "relax_v_15m"),
            (60 * 60, "relax_v_1h"),
            (12 * 60 * 60, "relax_v_12h"),
            (24 * 60 * 60, "relax_v_24h"),
        )
        updates = {}
        for threshold, field_name in windows:
            if elapsed >= threshold and getattr(self.evidence, field_name) is None:
                updates[field_name] = point.voltage_v
        if updates:
            self.evidence = replace(self.evidence, **updates)

    def observe(self, point: RecoveryTracePoint) -> SignalAnalysis:
        key = self._normalize_stage(point.stage)
        if key != self._stage_key:
            self._enter_stage(point)
        elif point.target_voltage_v != self._analyzer.target_voltage_v:
            # A voltage step inside a named stage is a new signal-analysis segment,
            # but does not erase already aggregated cycle evidence.
            self._analyzer.reset_stage(key, target_voltage_v=point.target_voltage_v)
            self._stage_started_at = point.timestamp_s
            self._stage_start_ah = point.ah

        analysis = self._analyzer.observe(
            SignalSample(
                timestamp_s=point.timestamp_s,
                voltage_v=point.voltage_v,
                current_a=point.current_a,
                temp_c=point.temp_c,
                is_cv=point.is_cv,
            )
        )
        if analysis.has(SignalEvent.TELEMETRY_INVALID):
            return analysis

        self._update_temperature(point, analysis)
        self._update_charge_stage(point, analysis)
        self._update_relaxation(point)
        return analysis

    def replay(self, points: Iterable[RecoveryTracePoint]) -> RecoveryCycleEvidence:
        for point in points:
            self.observe(point)
        return self.evidence

    def complete(
        self,
        *,
        completed_at: float,
        outcome: str = "",
        measured_capacity_ah: Optional[float] = None,
        cca_a: Optional[float] = None,
        internal_resistance_mohm: Optional[float] = None,
        notes: str = "",
    ) -> RecoveryCycleEvidence:
        self.evidence = replace(
            self.evidence,
            completed_at=float(completed_at),
            outcome=str(outcome),
            measured_capacity_ah=measured_capacity_ah,
            cca_a=cca_a,
            internal_resistance_mohm=internal_resistance_mohm,
            notes=str(notes),
        )
        return self.evidence


def replay_trace(
    raw_points: Iterable[Mapping[str, object]],
    *,
    battery_id: str,
    started_at: float,
    intent: ChargeIntent,
    condition_before: BatteryCondition = BatteryCondition.UNKNOWN,
) -> RecoveryCycleEvidence:
    tracker = RecoverySessionTracker(
        battery_id=battery_id,
        started_at=started_at,
        intent=intent,
        condition_before=condition_before,
    )
    points = (RecoveryTracePoint.from_mapping(raw) for raw in raw_points)
    return tracker.replay(points)
