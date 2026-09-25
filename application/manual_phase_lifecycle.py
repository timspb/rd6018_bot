"""V3-owned Manual phase decision contract.

This module is deliberately infrastructure-free.  It evaluates MAIN evidence
and produces a decision; it does not know HA, RD, ESPHome or a setter.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import time
from uuid import uuid4

from application.execution_intent.models import ExecutionIntent, SafetyContext


@dataclass(frozen=True)
class ManualPhaseDecision:
    decision_id: str
    phase_before: str
    phase_after: str
    voltage_v: float
    current_a: float
    reason: str
    timestamp: float
    execution_intent: ExecutionIntent


class ManualPhaseLifecycle:
    """Own MAIN→MIX evidence and target selection for the V3 Manual path."""

    def __init__(self) -> None:
        self.confirmations = 0
        self.hold_started_at: float | None = None
        self.last_confirmation_at = 0.0
        self.last_decision: ManualPhaseDecision | None = None

    def reset(self) -> None:
        self.confirmations = 0
        self.hold_started_at = None
        self.last_confirmation_at = 0.0
        self.last_decision = None

    def evaluate_main(
        self,
        *,
        profile,
        voltage_v: float,
        current_a: float,
        is_cv: bool,
        now: float | None = None,
    ) -> ManualPhaseDecision | None:
        if not is_cv or voltage_v < float(profile.main.voltage_v) - 0.20:
            return None
        threshold = profile.main.minimum_current_a
        if threshold is None or current_a > float(threshold):
            return None
        current_time = float(time() if now is None else now)
        interval = float(profile.main.confirmation_interval_seconds)
        if self.last_confirmation_at and current_time - self.last_confirmation_at < interval:
            return None
        self.last_confirmation_at = current_time
        self.confirmations += 1
        if self.confirmations < int(profile.main.confirmation_count):
            return None
        if self.hold_started_at is None:
            self.hold_started_at = current_time
            return None
        if current_time - self.hold_started_at < float(profile.main.hold_hours) * 3600.0:
            return None
        decision_id = uuid4().hex
        intent = ExecutionIntent(
            requested_voltage_v=float(profile.mix.voltage_v),
            requested_current_a=float(profile.mix.current_a),
            requested_mode="MANUAL_MIX_SETPOINT",
            source_decision_id=decision_id,
            safety_context=SafetyContext(
                telemetry_state="FRESH",
                lease_state="V2_PHYSICAL_OWNER",
                containment_state="NORMAL",
                verification_state="REQUIRED",
                limits_reference="existing V2 guarded setter policy",
            ),
        )
        self.last_decision = ManualPhaseDecision(
            decision_id=decision_id,
            phase_before="main",
            phase_after="mix",
            voltage_v=float(profile.mix.voltage_v),
            current_a=float(profile.mix.current_a),
            reason="MAIN minimum-current hold completed",
            timestamp=current_time,
            execution_intent=intent,
        )
        return self.last_decision


__all__ = ["ManualPhaseDecision", "ManualPhaseLifecycle"]
