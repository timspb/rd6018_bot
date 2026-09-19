"""Pure V3 recovery and audit-continuity contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from application.decision_audit import DecisionAuditEvent, DecisionAuditTrail
from application.execution_intent.models import ExecutionIntent
from application.physical_boundary.approval import ExecutionApproval
from application.safety.models import SafetyState


class RecoveryKind(str, Enum):
    RECOVER_EXISTING = "RECOVER_EXISTING"
    START_NEW = "START_NEW"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class V3RecoverySnapshot:
    session_id: str
    trace_id: str
    lifecycle_state: str
    program_id: str
    phase: str
    telemetry_fresh: bool
    safety_state: SafetyState
    pending_intent: ExecutionIntent | None
    approval: ExecutionApproval | None
    audit_cursor: int

    def __post_init__(self) -> None:
        for name in ("session_id", "trace_id", "lifecycle_state", "program_id", "phase"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} is required")
        if self.audit_cursor < 0:
            raise ValueError("audit cursor cannot be negative")


@dataclass(frozen=True)
class RecoveryDecision:
    kind: RecoveryKind
    snapshot: V3RecoverySnapshot | None
    execution_allowed: bool
    reason: str


class V3RecoveryCoordinator:
    """Classify persisted state without starting execution or fabricating events."""

    def decide(
        self,
        snapshot: V3RecoverySnapshot | None,
        *,
        legacy_state: bool = False,
        now: float = 0.0,
    ) -> RecoveryDecision:
        if snapshot is None:
            if legacy_state:
                return RecoveryDecision(RecoveryKind.AMBIGUOUS, None, False, "legacy snapshot has no V3 identity")
            return RecoveryDecision(RecoveryKind.START_NEW, None, False, "no persisted V3 recovery snapshot")

        if not snapshot.pending_intent:
            return RecoveryDecision(RecoveryKind.RECOVER_EXISTING, snapshot, False, "state recovered; no pending execution intent")
        approval = snapshot.approval
        if approval is None:
            return RecoveryDecision(RecoveryKind.RECOVER_EXISTING, snapshot, False, "pending intent has no approval")
        if approval.decision_id != snapshot.pending_intent.source_decision_id or approval.intent_id != snapshot.pending_intent.source_decision_id:
            return RecoveryDecision(RecoveryKind.RECOVER_EXISTING, snapshot, False, "approval does not match pending intent")
        if now >= approval.expiry:
            return RecoveryDecision(RecoveryKind.RECOVER_EXISTING, snapshot, False, "approval expired")
        if snapshot.safety_state not in {SafetyState.ALLOW, SafetyState.LIMIT}:
            return RecoveryDecision(RecoveryKind.RECOVER_EXISTING, snapshot, False, "safety state forbids recovery execution")
        if not snapshot.telemetry_fresh:
            return RecoveryDecision(RecoveryKind.RECOVER_EXISTING, snapshot, False, "telemetry is stale during recovery")
        return RecoveryDecision(RecoveryKind.RECOVER_EXISTING, snapshot, True, "state and approval are valid for recovery")


@dataclass(frozen=True)
class AuditContinuityResult:
    valid: bool
    trail: DecisionAuditTrail
    reason: str


class AuditContinuityValidator:
    """Validate an existing immutable prefix before appending post-restart events."""

    def continue_after_restart(
        self,
        trail: DecisionAuditTrail,
        audit_cursor: int,
        new_events: tuple[DecisionAuditEvent, ...] = (),
    ) -> AuditContinuityResult:
        if audit_cursor < 0 or audit_cursor > len(trail.events):
            return AuditContinuityResult(False, trail, "audit cursor is outside the existing trail")
        prefix = trail.events[:audit_cursor]
        if len({event.event_id for event in new_events}) != len(new_events):
            return AuditContinuityResult(False, trail, "post-restart events contain duplicate identities")
        existing_ids = {event.event_id for event in trail.events}
        if any(event.event_id in existing_ids for event in new_events):
            return AuditContinuityResult(False, trail, "post-restart event duplicates existing event")
        result = DecisionAuditTrail(prefix)
        try:
            for event in new_events:
                result = result.append(event)
        except ValueError as exc:
            return AuditContinuityResult(False, trail, str(exc))
        return AuditContinuityResult(True, result, "audit prefix preserved and new events appended")


__all__ = [
    "AuditContinuityResult",
    "AuditContinuityValidator",
    "RecoveryDecision",
    "RecoveryKind",
    "V3RecoverySnapshot",
    "V3RecoveryCoordinator",
]
