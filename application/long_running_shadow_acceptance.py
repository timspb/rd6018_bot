"""Long-running V3 shadow acceptance metrics; observation only."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .v2_v3_comparison import ComparisonStatus


class AcceptanceBand(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class LongRunThresholds:
    minimum_decisions: int = 100
    maximum_conflict_rate: float = 0.01
    maximum_unknown_rate: float = 0.0
    maximum_restarts: int = 0
    maximum_worker_failures: int = 0
    maximum_safety_divergence: int = 0
    maximum_configuration_conflicts: int = 0


@dataclass(frozen=True)
class DecisionMetrics:
    equal: int
    expected_difference: int
    conflict: int
    unknown: int

    @property
    def total(self) -> int:
        return self.equal + self.expected_difference + self.conflict + self.unknown

    @property
    def equal_rate(self) -> float:
        return self.equal / (self.total or 1)

    @property
    def expected_difference_rate(self) -> float:
        return self.expected_difference / (self.total or 1)

    @property
    def conflict_rate(self) -> float:
        return self.conflict / (self.total or 1)

    @property
    def unknown_rate(self) -> float:
        return self.unknown / (self.total or 1)


@dataclass(frozen=True)
class ExecutionMetrics:
    intent_total: int
    intent_equal: int
    safety_gate_total: int
    safety_gate_equal: int
    verification_total: int
    verification_equal: int


@dataclass(frozen=True)
class RuntimeMetrics:
    v2_health_samples: int
    v3_health_samples: int
    v2_unhealthy: int
    v3_unhealthy: int
    restart_events: int
    worker_failures: int


@dataclass(frozen=True)
class SafetyMetrics:
    containment_divergence: int
    lease_divergence: int
    stale_telemetry_events: int


@dataclass(frozen=True)
class ConfigurationMetrics:
    unresolved_usage: int
    provenance_conflicts: int


@dataclass(frozen=True)
class LongRunAcceptance:
    decision: DecisionMetrics
    execution: ExecutionMetrics
    runtime: RuntimeMetrics
    safety: SafetyMetrics
    configuration: ConfigurationMetrics
    decision_band: AcceptanceBand
    execution_band: AcceptanceBand
    runtime_band: AcceptanceBand
    safety_band: AcceptanceBand
    configuration_band: AcceptanceBand
    blockers: tuple[str, ...]
    ownership_changed: bool = False


class ShadowAcceptanceCollector:
    """Collect evidence counters and evaluate thresholds without ownership changes."""

    def __init__(self, *, thresholds: LongRunThresholds = LongRunThresholds()) -> None:
        self.thresholds = thresholds
        self._decisions = {status: 0 for status in ComparisonStatus}
        self._execution = [0, 0, 0, 0, 0, 0]
        self._runtime = [0, 0, 0, 0, 0, 0]
        self._safety = [0, 0, 0]
        self._configuration = [0, 0]

    def record_decision(self, status: ComparisonStatus) -> None:
        if not isinstance(status, ComparisonStatus):
            status = ComparisonStatus(status)
        self._decisions[status] += 1

    def record_execution(self, *, intent_equal: bool, safety_gate_equal: bool, verification_equal: bool) -> None:
        self._execution[0] += 1
        self._execution[1] += bool(intent_equal)
        self._execution[2] += 1
        self._execution[3] += bool(safety_gate_equal)
        self._execution[4] += 1
        self._execution[5] += bool(verification_equal)

    def record_runtime(self, *, v2_healthy: bool, v3_healthy: bool, restart: bool = False, worker_failure: bool = False) -> None:
        self._runtime[0] += 1
        self._runtime[1] += 1
        self._runtime[2] += not v2_healthy
        self._runtime[3] += not v3_healthy
        self._runtime[4] += restart
        self._runtime[5] += worker_failure

    def record_safety(self, *, containment_divergence: int = 0, lease_divergence: int = 0, stale_telemetry: int = 0) -> None:
        self._safety[0] += containment_divergence
        self._safety[1] += lease_divergence
        self._safety[2] += stale_telemetry

    def record_configuration(self, *, unresolved_usage: int = 0, provenance_conflict: int = 0) -> None:
        self._configuration[0] += unresolved_usage
        self._configuration[1] += provenance_conflict

    def evaluate(self) -> LongRunAcceptance:
        decision = DecisionMetrics(
            self._decisions[ComparisonStatus.EQUAL],
            self._decisions[ComparisonStatus.EXPECTED_DIFFERENCE],
            self._decisions[ComparisonStatus.CONFLICT],
            self._decisions[ComparisonStatus.UNKNOWN],
        )
        execution = ExecutionMetrics(*self._execution)
        runtime = RuntimeMetrics(*self._runtime)
        safety = SafetyMetrics(*self._safety)
        configuration = ConfigurationMetrics(*self._configuration)
        blockers: list[str] = []
        if decision.conflict_rate > self.thresholds.maximum_conflict_rate:
            blockers.append("decision_conflict_rate")
        if decision.unknown_rate > self.thresholds.maximum_unknown_rate:
            blockers.append("decision_unknown_rate")
        if execution.intent_equal < execution.intent_total or execution.safety_gate_equal < execution.safety_gate_total or execution.verification_equal < execution.verification_total:
            blockers.append("execution_parity")
        if runtime.v2_unhealthy or runtime.v3_unhealthy or runtime.restart_events > self.thresholds.maximum_restarts or runtime.worker_failures > self.thresholds.maximum_worker_failures:
            blockers.append("runtime_health")
        if safety.containment_divergence + safety.lease_divergence > self.thresholds.maximum_safety_divergence:
            blockers.append("safety_divergence")
        if configuration.provenance_conflicts > self.thresholds.maximum_configuration_conflicts or configuration.unresolved_usage:
            blockers.append("configuration_conflict")
        decision_band = AcceptanceBand.BLOCKED if blockers else AcceptanceBand.WARNING if decision.total < self.thresholds.minimum_decisions else AcceptanceBand.PASS
        execution_band = AcceptanceBand.BLOCKED if "execution_parity" in blockers else AcceptanceBand.PASS
        runtime_band = AcceptanceBand.BLOCKED if "runtime_health" in blockers else AcceptanceBand.PASS
        safety_band = AcceptanceBand.BLOCKED if "safety_divergence" in blockers else AcceptanceBand.PASS
        configuration_band = AcceptanceBand.BLOCKED if "configuration_conflict" in blockers else AcceptanceBand.PASS
        if decision.total == 0:
            blockers.append("no_decision_observations")
            decision_band = AcceptanceBand.BLOCKED
        return LongRunAcceptance(decision, execution, runtime, safety, configuration, decision_band, execution_band, runtime_band, safety_band, configuration_band, tuple(blockers))


__all__ = [
    "AcceptanceBand", "LongRunThresholds", "DecisionMetrics", "ExecutionMetrics",
    "RuntimeMetrics", "SafetyMetrics", "ConfigurationMetrics", "LongRunAcceptance",
    "ShadowAcceptanceCollector",
]
