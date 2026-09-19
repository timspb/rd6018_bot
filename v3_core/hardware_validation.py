"""Read-only real-contour validation contracts; no clients or writes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class RealValidationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    DEGRADED = "DEGRADED"
    CONFLICT = "CONFLICT"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class RealObservation:
    source: str
    timestamp: float
    age_s: float
    confidence: float
    available: bool
    values: dict[str, Any]

    @property
    def fresh(self) -> bool:
        return self.available and self.age_s <= 20.0


@dataclass(frozen=True)
class RealTelemetryValidationModel:
    freshness_limit_s: float = 20.0

    def validate(self, observations: tuple[RealObservation, ...]) -> RealValidationStatus:
        available = [item for item in observations if item.available]
        if not available:
            return RealValidationStatus.UNAVAILABLE
        if any(item.age_s > self.freshness_limit_s for item in available):
            return RealValidationStatus.DEGRADED
        if len(available) > 1:
            comparable = [tuple(sorted(item.values.items())) for item in available]
            if len(set(comparable)) > 1:
                return RealValidationStatus.CONFLICT
        if any(item.confidence <= 0 for item in available):
            return RealValidationStatus.DEGRADED
        return RealValidationStatus.VERIFIED


class ReadbackValidationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"
    MISMATCH = "MISMATCH"


@dataclass(frozen=True)
class RealReadbackObservation:
    command_id: str
    requested: dict[str, Any]
    observed: dict[str, Any] | None
    age_s: float
    available: bool
    matches: bool | None


class RealReadbackValidationModel:
    def __init__(self, freshness_limit_s: float = 20.0) -> None:
        self.freshness_limit_s = freshness_limit_s

    def validate(self, observation: RealReadbackObservation) -> ReadbackValidationStatus:
        if not observation.available or observation.observed is None:
            return ReadbackValidationStatus.UNAVAILABLE
        if observation.age_s > self.freshness_limit_s:
            return ReadbackValidationStatus.STALE
        if observation.matches is False:
            return ReadbackValidationStatus.MISMATCH
        if observation.matches is not True:
            return ReadbackValidationStatus.UNAVAILABLE
        return ReadbackValidationStatus.VERIFIED


@dataclass(frozen=True)
class ESPHomeObservationReport:
    entities: tuple[str, ...]
    observations: tuple[RealObservation, ...]
    lease_information: dict[str, Any]
    status: RealValidationStatus
    writes_performed: bool = False


@dataclass(frozen=True)
class HAObservationReport:
    entities: tuple[str, ...]
    observations: tuple[RealObservation, ...]
    availability: dict[str, bool]
    status: RealValidationStatus
    writes_performed: bool = False


class LeaseObservationStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DELAYED = "DELAYED"
    EXPIRED = "EXPIRED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class RealLeaseObservationReport:
    owner: str | None
    renewed_at: float | None
    expires_at: float | None
    status: LeaseObservationStatus
    fail_safe_observed: bool | None
    writes_performed: bool = False


class ShadowComparisonCategory(str, Enum):
    MATCH = "MATCH"
    EXPECTED_DIFFERENCE = "EXPECTED_DIFFERENCE"
    WARNING = "WARNING"
    BLOCKER = "BLOCKER"


@dataclass(frozen=True)
class ShadowComparisonResult:
    category: ShadowComparisonCategory
    v2_observed: dict[str, Any]
    v3_expected: dict[str, Any]
    reason: str


def compare_shadow_observation(v2_observed: dict[str, Any], v3_expected: dict[str, Any]) -> ShadowComparisonResult:
    if v2_observed == v3_expected:
        return ShadowComparisonResult(ShadowComparisonCategory.MATCH, v2_observed, v3_expected, "equal")
    if not v2_observed or not v3_expected:
        return ShadowComparisonResult(ShadowComparisonCategory.BLOCKER, v2_observed, v3_expected, "missing comparison evidence")
    return ShadowComparisonResult(ShadowComparisonCategory.WARNING, v2_observed, v3_expected, "observation differs from expectation")


__all__ = [
    "RealValidationStatus", "RealObservation", "RealTelemetryValidationModel",
    "ReadbackValidationStatus", "RealReadbackObservation", "RealReadbackValidationModel",
    "ESPHomeObservationReport", "HAObservationReport", "LeaseObservationStatus",
    "RealLeaseObservationReport", "ShadowComparisonCategory", "ShadowComparisonResult",
    "compare_shadow_observation",
]
