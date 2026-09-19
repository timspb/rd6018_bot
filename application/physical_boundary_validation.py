"""Non-actuating physical-boundary validation models for Workstream 5."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


class CapabilityStatus(str, Enum):
    READY = "READY"
    NEEDS_VALIDATION = "NEEDS_VALIDATION"
    BLOCKED = "BLOCKED"
    LEGACY_ONLY = "LEGACY_ONLY"


@dataclass(frozen=True)
class PhysicalExecutionCapability:
    operation: str
    owner: str
    adapter: str
    transport: str
    target: str
    verification_method: str
    rollback_method: str
    status: CapabilityStatus


def physical_execution_capability_map() -> tuple[PhysicalExecutionCapability, ...]:
    """Describe the target V3 path without constructing an adapter."""
    return tuple(
        PhysicalExecutionCapability(
            operation,
            "V3 Execution Boundary",
            "V3 Physical Adapter (not connected)",
            "RD transport (not configured)",
            target,
            verification,
            rollback,
            CapabilityStatus.BLOCKED,
        )
        for operation, target, verification, rollback in (
            ("OUTPUT_ON", "RD6018 output", "output-state + programmed V/I/OVP/OCP readback", "verified OUTPUT_OFF"),
            ("OUTPUT_OFF", "RD6018 output", "fresh output-state OFF readback", "retry then containment/latch"),
            ("SET_VOLTAGE", "RD6018 voltage", "fresh voltage setpoint/readback", "restore previous or verified OFF"),
            ("SET_CURRENT", "RD6018 current", "fresh current setpoint/readback", "restore previous or verified OFF"),
            ("STOP", "RD6018 output/session", "verified OFF plus session state", "contain and require operator reauthorization"),
            ("CONTAINMENT", "RD6018 output", "verified OFF or explicit UNKNOWN/FAILED", "contain and latch"),
        )
    )


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    MISSING = "MISSING_READBACK"
    STALE = "STALE_READBACK"
    MISMATCH = "READBACK_MISMATCH"
    UNAVAILABLE = "READBACK_UNAVAILABLE"


@dataclass(frozen=True)
class ReadbackVerificationResult:
    status: VerificationStatus
    expected: Any
    observed: Any
    age_s: float | None
    reason: str


class ReadbackVerificationModel:
    """Pure command/readback verifier; it never sends or retries commands."""

    @staticmethod
    def verify(
        *,
        expected: Any,
        observed: Any,
        observed_at: datetime | None,
        now: datetime,
        timeout_s: float,
        tolerance: float = 0.0,
    ) -> ReadbackVerificationResult:
        if observed is None:
            return ReadbackVerificationResult(VerificationStatus.MISSING, expected, observed, None, "readback_missing")
        if observed_at is None:
            return ReadbackVerificationResult(VerificationStatus.UNAVAILABLE, expected, observed, None, "readback_timestamp_missing")
        age_s = max(0.0, (now - observed_at).total_seconds())
        if age_s > timeout_s:
            return ReadbackVerificationResult(VerificationStatus.STALE, expected, observed, age_s, "readback_stale")
        try:
            matches = abs(float(expected) - float(observed)) <= tolerance
        except (TypeError, ValueError):
            matches = expected == observed
        if not matches:
            return ReadbackVerificationResult(VerificationStatus.MISMATCH, expected, observed, age_s, "readback_mismatch")
        return ReadbackVerificationResult(VerificationStatus.VERIFIED, expected, observed, age_s, "readback_verified")


class LeaseParityStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    UNAVAILABLE = "UNAVAILABLE"
    DUPLICATE_OWNER = "DUPLICATE_OWNER"


@dataclass(frozen=True)
class LeaseParityValidationModel:
    current_owner: str
    renewal_path: str
    ttl_s: float
    renewal_interval_s: float
    fail_safe: str

    def validate(self, *, status: LeaseParityStatus, owners: tuple[str, ...] = ()) -> str:
        if len(set(owners)) > 1:
            return LeaseParityStatus.DUPLICATE_OWNER.value
        if status is LeaseParityStatus.EXPIRED:
            return "CONTAINMENT_REQUIRED"
        if status is LeaseParityStatus.UNAVAILABLE:
            return "UNKNOWN_REQUIRES_FAIL_SAFE"
        return "LEASE_ACTIVE"


def current_lease_parity_model() -> LeaseParityValidationModel:
    return LeaseParityValidationModel(
        current_owner="ESPHome/edge dead-man",
        renewal_path="V2 EdgeSafetyLease renewal contract",
        ttl_s=900.0,
        renewal_interval_s=300.0,
        fail_safe="local dead-man expires to safe output state",
    )


@dataclass(frozen=True)
class SafetyPhysicalBoundaryRecord:
    stage: str
    owner: str
    next_boundary: str
    trace_required: bool
    status: str


def safety_physical_boundary_report() -> tuple[SafetyPhysicalBoundaryRecord, ...]:
    return (
        SafetyPhysicalBoundaryRecord("DETECTION", "V3 Safety Domain", "Safety Decision", True, "MODELED"),
        SafetyPhysicalBoundaryRecord("SAFETY_DECISION", "V3 Safety Domain", "Containment Request", True, "MODELED"),
        SafetyPhysicalBoundaryRecord("CONTAINMENT", "V3 Execution Boundary", "Execution Adapter", True, "SHADOW_ONLY"),
        SafetyPhysicalBoundaryRecord("EXECUTION", "V3 Physical Adapter", "Readback Verification", True, "BLOCKED"),
        SafetyPhysicalBoundaryRecord("VERIFICATION", "V3 Readback Model", "Final state", True, "MODEL_ONLY"),
    )


__all__ = [
    "CapabilityStatus", "PhysicalExecutionCapability", "physical_execution_capability_map",
    "VerificationStatus", "ReadbackVerificationResult", "ReadbackVerificationModel",
    "LeaseParityStatus", "LeaseParityValidationModel", "current_lease_parity_model",
    "SafetyPhysicalBoundaryRecord", "safety_physical_boundary_report",
]
