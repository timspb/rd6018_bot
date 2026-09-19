"""Live-input read-only Canary preflight evaluation; no activation or execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .canary_preflight import CanaryPreflightValidator, CheckResult, PreflightCheck, PreflightStatus
from v3_core.canary_readiness import CanaryApprovalGate, V3CanaryReadinessMatrix


@dataclass(frozen=True)
class CurrentPreflightContext:
    timestamp: float
    system_health: Any
    evidence: Any
    diagnostics: Sequence[Any]
    readiness_matrix: V3CanaryReadinessMatrix
    active_blockers: Sequence[Any]
    approval: CanaryApprovalGate | None
    rollback_ready: bool
    rollback_owner: str | None
    external_availability: Mapping[str, str]
    lease_observation: Mapping[str, Any]


@dataclass(frozen=True)
class LiveCanaryPreflightResult:
    status: PreflightStatus
    checks: tuple[PreflightCheck, ...]
    blockers: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    evaluated_at: float


class LiveCanaryPreflightEvaluator:
    """Evaluates an already-collected live context; has no source clients."""

    def __init__(self, validator: CanaryPreflightValidator | None = None) -> None:
        self._validator = validator or CanaryPreflightValidator()

    def evaluate(self, context: CurrentPreflightContext) -> LiveCanaryPreflightResult:
        base = self._validator.validate(
            readiness_matrix=context.readiness_matrix,
            current_health=context.system_health,
            shadow_evidence=context.evidence,
            diagnostics=context.diagnostics,
            approval=context.approval,
            blocker_registry=context.active_blockers,
            now=context.timestamp,
            rollback_ready=context.rollback_ready,
            rollback_owner=context.rollback_owner,
        )
        checks = list(base.checks)
        external_bad = tuple(name for name, status in context.external_availability.items() if str(status).upper() not in {"PASS", "MATCHED", "VERIFIED"})
        if external_bad:
            checks.append(PreflightCheck("external_parity", CheckResult.BLOCKED, ", ".join(f"{name}={context.external_availability[name]}" for name in external_bad), "external parity incomplete"))
        lease = context.lease_observation
        lease_ok = bool(lease.get("owner")) and bool(lease.get("active")) and not bool(lease.get("tripped")) and float(lease.get("remaining_s", 0)) > 0 and float(lease.get("modbus_age_s", 99999)) <= 20
        if not lease_ok:
            checks.append(PreflightCheck("lease_safety", CheckResult.BLOCKED, "lease observation incomplete/unsafe", "lease or safety state is not proven"))
        elif float(lease.get("armed_age_s", 0)) > 300:
            checks.append(PreflightCheck("lease_freshness", CheckResult.BLOCKED, f"armed_age={lease['armed_age_s']:.1f}s", "armed state is stale"))
        blockers = tuple(check.blocker for check in checks if check.blocker)
        status = PreflightStatus.BLOCKED if any(check.result.value == "BLOCKED" for check in checks) else (PreflightStatus.WARNING if any(check.result.value == "WARNING" for check in checks) else PreflightStatus.ALLOWED)
        refs = tuple(str(getattr(item, "evidence_id", "")) for item in (context.evidence,) if getattr(item, "evidence_id", None))
        return LiveCanaryPreflightResult(status, tuple(checks), blockers, refs, context.timestamp)


__all__ = ["CurrentPreflightContext", "LiveCanaryPreflightResult", "LiveCanaryPreflightEvaluator"]
