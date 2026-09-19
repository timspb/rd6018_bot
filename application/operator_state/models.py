"""Immutable canonical current-state snapshot for the read-only operator UI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Tuple

from application.charge_engine.models import TelemetrySnapshot
from application.charge_program.models import ChargeProgram
from application.charge_lifecycle import ChargeLifecycleSnapshot


class BatteryOwnership(str, Enum):
    BATTERY_DOMAIN = "Battery domain"


class ProgramOwnership(str, Enum):
    CHARGE_PROGRAM_DOMAIN = "ChargeProgram domain"


class LifecycleOwnership(str, Enum):
    LIFECYCLE_DOMAIN = "Lifecycle domain"


class TelemetryOwnership(str, Enum):
    TELEMETRY_DOMAIN = "Telemetry domain"


class SafetyOwnership(str, Enum):
    SAFETY_DOMAIN = "Safety domain"


class PhaseLifecycleState(str, Enum):
    ACTIVE = "ACTIVE"
    WAITING = "WAITING"
    RECOVERING = "RECOVERING"
    UNKNOWN = "UNKNOWN"


class CCVState(str, Enum):
    CC = "CC"
    CV = "CV"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class SafetyView:
    protection_state: str
    stale_state: str
    confidence: str
    active_faults: Tuple[str, ...] = ()


@dataclass(frozen=True)
class TelemetryView:
    voltage_v: float | None
    current_a: float | None
    power_w: float | None
    temperature_c: float | None
    ccv_state: CCVState
    timestamp: float | None
    freshness: str


@dataclass(frozen=True)
class OperatorStateSnapshot:
    battery_identity: str
    battery_profile: str
    chemistry: str
    mode: str
    program_id: str
    current_phase: str
    phase_state: PhaseLifecycleState
    phase_evidence: Tuple[str, ...]
    target_voltage_v: float | None
    target_current_a: float | None
    active_policies: Tuple[str, ...]
    telemetry: TelemetryView
    safety: SafetyView
    lifecycle_status: str
    session_id: str | None
    trace_id: str | None
    explanation: str
    waiting_conditions: Tuple[str, ...]
    next_transition: str | None

    def __post_init__(self) -> None:
        for name in ("battery_identity", "battery_profile", "chemistry", "mode", "program_id", "current_phase"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} is required")


class OperatorStateBuilder:
    """Build one current-state snapshot from canonical domain contracts only."""

    def build(
        self,
        program: ChargeProgram,
        *,
        phase: str,
        telemetry: TelemetrySnapshot,
        lifecycle: ChargeLifecycleSnapshot | None = None,
        lifecycle_status: str | None = None,
        safety: SafetyView | None = None,
        phase_state: PhaseLifecycleState = PhaseLifecycleState.ACTIVE,
        ccv_state: CCVState = CCVState.UNKNOWN,
    ) -> OperatorStateSnapshot:
        configured = next((item for item in program.phases if item.phase_id.upper() == phase.upper()), None)
        target_v = float(configured.voltage.target.value) if configured else None
        target_i = float(configured.current.target.value) if configured else None
        policies = tuple(item.name for item in configured.timers) if configured else ()
        transition = next((item for item in program.transitions if item.source_phase.upper() == phase.upper()), None)
        waiting = tuple(item.condition_key for item in program.transitions if item.source_phase.upper() == phase.upper())
        if transition is not None:
            next_transition = transition.target_phase
            explanation = f"{phase} selected by program {program.program_id}; next transition requires {transition.condition_key}"
        else:
            next_transition = None
            explanation = f"{phase} selected by program {program.program_id}; no next transition evidence"
        lifecycle_status = lifecycle_status or ("RESUME_EXISTING" if lifecycle else "AMBIGUOUS")
        return OperatorStateSnapshot(
            program.battery_profile.battery_id,
            program.battery_profile.model or program.battery_profile.manufacturer or program.battery_profile.battery_id,
            program.chemistry.value,
            program.mode.value,
            program.program_id,
            phase,
            phase_state,
            lifecycle.phase_evidence if lifecycle else (),
            target_v,
            target_i,
            policies,
            TelemetryView(telemetry.voltage_v, telemetry.current_a, (telemetry.voltage_v * telemetry.current_a if telemetry.voltage_v is not None and telemetry.current_a is not None else None), telemetry.temperature_c, ccv_state, telemetry.timestamp, "FRESH" if telemetry.complete else "STALE" if telemetry.fresh else "MISSING"),
            safety or SafetyView("UNKNOWN", "UNKNOWN", "LOW"),
            lifecycle_status,
            lifecycle.session_id if lifecycle else None,
            lifecycle.trace_id if lifecycle else None,
            explanation,
            waiting,
            next_transition,
        )


__all__ = [
    "BatteryOwnership", "CCVState", "LifecycleOwnership", "OperatorStateSnapshot",
    "OperatorStateBuilder", "PhaseLifecycleState", "ProgramOwnership",
    "SafetyOwnership", "SafetyView", "TelemetryView",
]
