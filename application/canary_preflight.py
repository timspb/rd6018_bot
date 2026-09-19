"""Read-only V3 canary preflight evaluator; it cannot activate or execute."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence

from v3_core.canary_readiness import CanaryApprovalGate, ReadinessStatus, V3CanaryReadinessMatrix


class PreflightStatus(str, Enum):
    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"
    WARNING = "WARNING"


class CheckResult(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    result: CheckResult
    evidence: str
    blocker: str | None = None


@dataclass(frozen=True)
class CanaryPreflightResult:
    status: PreflightStatus
    checks: tuple[PreflightCheck, ...]
    evaluated_at: float
    evidence_freshness_s: float | None
    failed_checks: tuple[str, ...]
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class CanaryPreflightSnapshot:
    status: PreflightStatus
    failed_checks: tuple[str, ...]
    blockers: tuple[str, ...]
    last_evaluation_time: float
    evidence_freshness_s: float | None


class CanaryPreflightValidator:
    """Evaluates supplied snapshots only; no owner or execution mutation exists."""

    def validate(
        self,
        *,
        readiness_matrix: V3CanaryReadinessMatrix,
        current_health: Any,
        shadow_evidence: Any,
        diagnostics: Sequence[Any],
        approval: CanaryApprovalGate | None,
        blocker_registry: Sequence[Any],
        now: float,
        rollback_ready: bool,
        rollback_owner: str | None,
        freshness_warning_s: float = 300.0,
        freshness_block_s: float = 900.0,
    ) -> CanaryPreflightResult:
        checks: list[PreflightCheck] = []
        readiness_blocked = readiness_matrix.status is ReadinessStatus.BLOCKED
        checks.append(PreflightCheck("readiness_matrix", CheckResult.BLOCKED if readiness_blocked else CheckResult.PASS, readiness_matrix.status.value, "readiness matrix contains blockers" if readiness_blocked else None))

        evidence_created = getattr(shadow_evidence, "created_at", None) if shadow_evidence is not None else None
        evidence_freshness = None if evidence_created is None else max(0.0, now - float(evidence_created))
        evidence_complete = bool(shadow_evidence is not None and getattr(shadow_evidence, "evidence_id", None) and getattr(shadow_evidence, "session_id", None) and getattr(shadow_evidence, "trace_id", None) and evidence_created)
        if not evidence_complete:
            checks.append(PreflightCheck("shadow_evidence", CheckResult.BLOCKED, "missing evidence identity/timestamp", "shadow evidence is required"))
        elif evidence_freshness is not None and evidence_freshness > freshness_block_s:
            checks.append(PreflightCheck("shadow_evidence", CheckResult.BLOCKED, f"age={evidence_freshness:.1f}s", "evidence is too old"))
        elif evidence_freshness is not None and evidence_freshness > freshness_warning_s:
            checks.append(PreflightCheck("shadow_evidence", CheckResult.WARNING, f"age={evidence_freshness:.1f}s", "evidence freshness warning"))
        else:
            checks.append(PreflightCheck("shadow_evidence", CheckResult.PASS, f"age={evidence_freshness:.1f}s" if evidence_freshness is not None else "fresh"))

        overall = getattr(current_health, "overall", None) if current_health is not None else None
        overall_value = getattr(overall, "value", str(overall)).upper() if overall is not None else ""
        health_ok = overall_value == "HEALTHY"
        checks.append(PreflightCheck("health", CheckResult.PASS if health_ok else CheckResult.BLOCKED, "overall healthy" if health_ok else "health unavailable/degraded", None if health_ok else "current health is not healthy"))
        approval_ok = approval is not None and approval.approved and approval.expires_at is not None and now < approval.expires_at
        checks.append(PreflightCheck("approval", CheckResult.PASS if approval_ok else CheckResult.BLOCKED, "owner/expiry valid" if approval_ok else "missing, revoked or expired approval", None if approval_ok else "approval gate is not valid"))
        rollback_ok = bool(rollback_ready and rollback_owner)
        checks.append(PreflightCheck("rollback", CheckResult.PASS if rollback_ok else CheckResult.BLOCKED, "procedure and owner present" if rollback_ok else "rollback procedure/owner missing", None if rollback_ok else "rollback readiness is required"))
        checks.append(PreflightCheck("diagnostics", CheckResult.PASS if diagnostics else CheckResult.WARNING, f"references={len(diagnostics)}", None if diagnostics else "no diagnostic references supplied"))

        for item in blocker_registry:
            active = bool(getattr(item, "active", True)) if not isinstance(item, Mapping) else bool(item.get("active", True))
            if active:
                description = getattr(item, "description", str(item)) if not isinstance(item, Mapping) else str(item.get("description", item))
                checks.append(PreflightCheck("blocker_registry", CheckResult.BLOCKED, description, description))

        blockers = tuple(check.blocker for check in checks if check.result is CheckResult.BLOCKED and check.blocker)
        failed = tuple(check.name for check in checks if check.result is not CheckResult.PASS)
        if blockers:
            status = PreflightStatus.BLOCKED
        elif failed:
            status = PreflightStatus.WARNING
        else:
            status = PreflightStatus.ALLOWED
        return CanaryPreflightResult(status, tuple(checks), now, evidence_freshness, failed, blockers)

    @staticmethod
    def snapshot(result: CanaryPreflightResult) -> CanaryPreflightSnapshot:
        return CanaryPreflightSnapshot(result.status, result.failed_checks, result.blockers, result.evaluated_at, result.evidence_freshness_s)


__all__ = ["PreflightStatus", "CheckResult", "PreflightCheck", "CanaryPreflightResult", "CanaryPreflightSnapshot", "CanaryPreflightValidator"]
