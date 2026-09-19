"""Pure parity models for Workstream 7; no transport or hardware access."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .contracts import SafetyAction, SafetyDecision, SafetySignal


class ParityStatus(str, Enum):
    VALIDATED = "VALIDATED"
    NEEDS_PARITY = "NEEDS_PARITY"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class SafetyTriggerOwnership:
    trigger: str
    source: str
    detector: str
    decision_owner: str
    containment_action: str
    execution_path: str
    verification: str
    status: ParityStatus


def safety_trigger_ownership_map() -> tuple[SafetyTriggerOwnership, ...]:
    return tuple(
        SafetyTriggerOwnership(trigger, source, detector, "V3 Safety Domain", action, "V3 Execution Boundary", verification, ParityStatus.NEEDS_PARITY)
        for trigger, source, detector, action, verification in (
            ("watchdog_timeout", "runtime watchdog observation", "watchdog detector", "containment/output-off intent", "fresh OFF readback"),
            ("telemetry_loss", "telemetry authority", "telemetry freshness detector", "containment/output-off intent", "fresh telemetry + OFF readback"),
            ("transport_failure", "transport result", "transport parity detector", "defer or containment intent", "explicit transport result"),
            ("lease_expiry", "lease observation", "lease parity detector", "dead-man containment", "edge state and OFF verification"),
            ("manual_stop", "operator intent", "operator boundary", "STOP/output-off intent", "fresh OFF readback"),
            ("emergency_stop", "safety signal", "emergency detector", "latched containment intent", "OFF or explicit failure"),
            ("invalid_state", "domain state", "state validator", "containment intent", "fresh state validation"),
            ("readback_mismatch", "readback verifier", "verification layer", "rollback/containment intent", "new readback or latch"),
        )
    )


class LeaseScenario(str, Enum):
    VALID = "lease_valid"
    EXPIRED = "lease_expired"
    RENEWAL_FAILURE = "renewal_failure"
    DUPLICATE_OWNER = "duplicate_lease_owner"
    RESTART = "restart_during_lease"


@dataclass(frozen=True)
class LeaseParityCase:
    scenario: LeaseScenario
    expected_behavior: str
    rollback: str
    verification: str
    status: ParityStatus


@dataclass(frozen=True)
class LeaseParityReport:
    current_owner: str
    renewal_path: str
    ttl_s: float
    renewal_interval_s: float
    fail_safe: str
    v3_authority: str
    cases: tuple[LeaseParityCase, ...]


def lease_parity_report() -> LeaseParityReport:
    cases = (
        LeaseParityCase(LeaseScenario.VALID, "continue only while fresh lease proof exists", "retain current owner", "armed/generation/remaining/readback", ParityStatus.NEEDS_PARITY),
        LeaseParityCase(LeaseScenario.EXPIRED, "dead-man containment", "verified OFF or latched failure", "edge expiry plus OFF state", ParityStatus.NEEDS_PARITY),
        LeaseParityCase(LeaseScenario.RENEWAL_FAILURE, "do not assume renewal; allow dead-man", "contain and require reauthorization", "renew ACK and remaining TTL", ParityStatus.NEEDS_PARITY),
        LeaseParityCase(LeaseScenario.DUPLICATE_OWNER, "reject V3 lease authority", "keep one current owner", "owner identity audit", ParityStatus.BLOCKED),
        LeaseParityCase(LeaseScenario.RESTART, "no automatic resume", "fresh operator/lease authorization", "fresh lease and actuator state", ParityStatus.NEEDS_PARITY),
    )
    return LeaseParityReport("ESPHome/edge dead-man", "existing V2 EdgeSafetyLease renewal", 900.0, 300.0, "local dead-man containment", "separate V3 lease abstraction after parity", cases)


class TransportParityState(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    REJECTED = "rejected"
    DELAYED = "delayed"
    CORRUPTED_RESPONSE = "corrupted_response"


@dataclass(frozen=True)
class TransportParityObservation:
    state: TransportParityState
    accepted: bool
    observed: object | None
    verified: bool
    reason: str


class TransportParityModel:
    def evaluate(self, state: TransportParityState, *, observed: object | None = None, expected: object | None = None) -> TransportParityObservation:
        if state is TransportParityState.AVAILABLE:
            verified = observed == expected
            return TransportParityObservation(state, True, observed, verified, "verified" if verified else "readback_mismatch")
        if state is TransportParityState.DELAYED:
            return TransportParityObservation(state, True, observed, False, "await_fresh_readback")
        if state is TransportParityState.TIMEOUT:
            return TransportParityObservation(state, False, None, False, "transport_timeout")
        if state is TransportParityState.UNAVAILABLE:
            return TransportParityObservation(state, False, None, False, "transport_unavailable")
        if state is TransportParityState.REJECTED:
            return TransportParityObservation(state, False, observed, False, "command_rejected")
        return TransportParityObservation(state, True, observed, False, "corrupted_response")


class TelemetryState(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    UNAVAILABLE = "unavailable"
    CONFLICTING = "conflicting"


def telemetry_safety_decision(state: TelemetryState, trace_id: str) -> SafetyDecision:
    healthy = state is TelemetryState.FRESH
    reason = "telemetry_fresh" if healthy else f"telemetry_{state.value}"
    return SafetyDecision(SafetyAction.ALLOW if healthy else SafetyAction.CONTAIN, reason, trace_id, "V3 Safety Domain")


class RestartScenario(str, Enum):
    DURING_CHARGE = "restart_during_charging"
    DURING_CONTAINMENT = "restart_during_containment"
    STALE_ACTUATOR = "restart_with_stale_actuator_state"
    NO_TELEMETRY = "restart_without_telemetry"
    NO_LEASE = "restart_without_lease"


@dataclass(frozen=True)
class RestartRecoveryCase:
    scenario: RestartScenario
    expected_behavior: str
    actuator_verification: str
    safety_verification: str
    status: ParityStatus


def restart_recovery_validation_model() -> tuple[RestartRecoveryCase, ...]:
    return tuple(
        RestartRecoveryCase(scenario, "no automatic unsafe resume", "fresh actuator/readback required", "fresh safety/lease validation required", ParityStatus.NEEDS_PARITY)
        for scenario in RestartScenario
    )


@dataclass(frozen=True)
class BenchValidationCase:
    name: str
    setup: str
    expected: str
    observed: str
    pass_criteria: str


def bench_validation_matrix() -> tuple[BenchValidationCase, ...]:
    return (
        BenchValidationCase("normal_command", "isolated bench transport available", "command accepted", "record transport/readback", "fresh matching readback"),
        BenchValidationCase("transport_timeout", "delay beyond configured timeout", "explicit timeout", "no assumed success", "containment/rollback trace"),
        BenchValidationCase("wrong_readback", "return mismatched state", "verification failure", "mismatch result", "rollback or latch"),
        BenchValidationCase("stale_telemetry", "age telemetry beyond limit", "containment recommendation", "stale state", "no unsafe resume"),
        BenchValidationCase("lease_loss", "expire lease observation", "dead-man remains final", "expiry/containment result", "verified safe state or latch"),
        BenchValidationCase("safety_trigger", "inject each safety trigger", "one traceable containment request", "decision and verification record", "single decision owner"),
        BenchValidationCase("restart_recovery", "restart during each listed state", "fresh validation required", "recovery candidate only", "operator authorization before resume"),
    )


__all__ = [
    "ParityStatus", "SafetyTriggerOwnership", "safety_trigger_ownership_map",
    "LeaseScenario", "LeaseParityCase", "LeaseParityReport", "lease_parity_report",
    "TransportParityState", "TransportParityObservation", "TransportParityModel",
    "TelemetryState", "telemetry_safety_decision", "RestartScenario", "RestartRecoveryCase",
    "restart_recovery_validation_model", "BenchValidationCase", "bench_validation_matrix",
]
