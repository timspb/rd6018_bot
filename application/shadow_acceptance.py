"""Objective V3 shadow acceptance criteria for Phase 10.2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .divergence_explanation import DivergenceCategory
from .shadow_evidence import ShadowEvidenceRecord
from .v2_v3_comparison import ComparisonStatus


class AcceptanceStatus(str, Enum):
    NOT_READY = "NOT_READY"
    OBSERVATION_READY = "OBSERVATION_READY"
    SHADOW_ACCEPTED = "SHADOW_ACCEPTED"
    OWNERSHIP_CANDIDATE = "OWNERSHIP_CANDIDATE"


@dataclass(frozen=True)
class DecisionParityMetrics:
    observations: int
    equal_rate: float
    expected_divergence_rate: float
    unexpected_conflict_rate: float


@dataclass(frozen=True)
class SafetyParityMetrics:
    safety_conflicts: int
    containment_conflicts: int
    telemetry_interpretation_conflicts: int


@dataclass(frozen=True)
class ConfigurationStability:
    unresolved_configs: int
    conflicting_sources: int
    missing_authority: int


@dataclass(frozen=True)
class TransportReadiness:
    ha_telemetry_ready: bool
    esp_telemetry_ready: bool
    arbitration_stable: bool


@dataclass(frozen=True)
class ExecutionReadiness:
    intent_parity: bool
    rollback_policy_covered: bool
    verification_coverage: bool


@dataclass(frozen=True)
class AcceptanceThresholds:
    minimum_observations: int = 100
    maximum_unexpected_conflict_rate: float = 0.01


@dataclass(frozen=True)
class ShadowAcceptanceResult:
    status: AcceptanceStatus
    decision_parity: DecisionParityMetrics
    safety_parity: SafetyParityMetrics
    configuration: ConfigurationStability
    transport: TransportReadiness
    execution: ExecutionReadiness
    blockers: tuple[str, ...]


class ShadowAcceptanceModel:
    """Calculate acceptance status without changing any ownership boundary."""

    def evaluate(
        self,
        evidence: Iterable[ShadowEvidenceRecord],
        *,
        configuration: ConfigurationStability,
        transport: TransportReadiness,
        execution: ExecutionReadiness,
        thresholds: AcceptanceThresholds = AcceptanceThresholds(),
        ownership_approval: bool = False,
    ) -> ShadowAcceptanceResult:
        records = tuple(evidence)
        total = len(records)
        equal = sum(record.comparison.status is ComparisonStatus.EQUAL for record in records)
        expected = sum(record.comparison.status is ComparisonStatus.EXPECTED_DIFFERENCE for record in records)
        conflicts = sum(record.comparison.status is ComparisonStatus.CONFLICT for record in records)
        divisor = total or 1
        parity = DecisionParityMetrics(total, equal / divisor, expected / divisor, conflicts / divisor)

        safety_conflicts = sum(self._has_category(record, DivergenceCategory.SAFETY_DIFF) for record in records)
        containment = sum(
            1 for record in records
            if any(item.category is DivergenceCategory.SAFETY_DIFF and "containment" in item.reason for item in record.divergence_explanation.explanations)
        )
        telemetry = sum(
            1 for record in records
            if any(item.category is DivergenceCategory.UNKNOWN and "telemetry" in item.reason.lower() for item in record.divergence_explanation.explanations)
        )
        safety_metrics = SafetyParityMetrics(safety_conflicts, containment, telemetry)

        blockers: list[str] = []
        if total == 0:
            blockers.append("no_shadow_observations")
        if configuration.unresolved_configs or configuration.conflicting_sources or configuration.missing_authority:
            blockers.append("configuration_unresolved")
        if safety_conflicts or containment or telemetry:
            blockers.append("safety_parity_not_proven")
        if not (transport.ha_telemetry_ready and transport.esp_telemetry_ready and transport.arbitration_stable):
            blockers.append("transport_readiness_not_proven")
        if not (execution.intent_parity and execution.rollback_policy_covered and execution.verification_coverage):
            blockers.append("execution_coverage_incomplete")
        if total and parity.unexpected_conflict_rate > thresholds.maximum_unexpected_conflict_rate:
            blockers.append("unexpected_conflict_rate_exceeded")

        if not total or blockers:
            status = AcceptanceStatus.NOT_READY if not total or "safety_parity_not_proven" in blockers or "configuration_unresolved" in blockers else AcceptanceStatus.OBSERVATION_READY
        elif total < thresholds.minimum_observations:
            status = AcceptanceStatus.OBSERVATION_READY
            blockers.append("observation_volume_below_threshold")
        elif ownership_approval:
            status = AcceptanceStatus.OWNERSHIP_CANDIDATE
        else:
            status = AcceptanceStatus.SHADOW_ACCEPTED
        return ShadowAcceptanceResult(status, parity, safety_metrics, configuration, transport, execution, tuple(blockers))

    @staticmethod
    def _has_category(record: ShadowEvidenceRecord, category: DivergenceCategory) -> bool:
        return any(item.category is category for item in record.divergence_explanation.explanations)


__all__ = [
    "AcceptanceStatus", "DecisionParityMetrics", "SafetyParityMetrics",
    "ConfigurationStability", "TransportReadiness", "ExecutionReadiness",
    "AcceptanceThresholds", "ShadowAcceptanceResult", "ShadowAcceptanceModel",
]
