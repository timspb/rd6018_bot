"""Read-only diagnostic authority to SafetyEvidence mapping."""

from __future__ import annotations

from dataclasses import dataclass

from .models import DiagnosticAuthority, DiagnosticDecision


@dataclass(frozen=True)
class SafetyEvidence:
    allowed: bool
    authority: DiagnosticAuthority
    reason: str
    source: str
    timestamp: float
    evidence_refs: tuple[str, ...] = ()
    severity: str = "info"
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not self.reason.strip() or not self.source.strip():
            raise ValueError("safety evidence reason and source are required")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("safety evidence confidence must be between 0 and 1")


def safety_evidence_from_diagnostic(
    decision: DiagnosticDecision, *, timestamp: float, source: str = "battery_diagnostics"
) -> SafetyEvidence:
    allowed = decision.authority is DiagnosticAuthority.ALLOW
    reason = ",".join(decision.reasons) or decision.authority.value
    return SafetyEvidence(
        allowed=allowed,
        authority=decision.authority,
        reason=reason,
        source=source,
        timestamp=timestamp,
        evidence_refs=decision.reasons,
        severity="critical" if decision.hard_stop else ("error" if not allowed else "info"),
        confidence=1.0,
    )


def evaluate_safety_evidence(evidence: SafetyEvidence) -> bool:
    """Shadow-only gate result; no OutputIntent is created."""
    return evidence.allowed and evidence.authority is DiagnosticAuthority.ALLOW


def combine_safety_evidence(evidence: tuple[SafetyEvidence, ...]) -> SafetyEvidence:
    """Apply the fail-closed authority order without creating an actuator action."""
    if not evidence:
        raise ValueError("at least one safety evidence item is required")
    priority = {
        DiagnosticAuthority.ALLOW: 0,
        DiagnosticAuthority.VERIFY_BEFORE_HV: 1,
        DiagnosticAuthority.BLOCK_AUTOMATIC_HV: 2,
        DiagnosticAuthority.HARD_STOP: 3,
    }
    highest = max(evidence, key=lambda item: priority[item.authority])
    allowed = all(item.allowed and item.authority is DiagnosticAuthority.ALLOW for item in evidence)
    return SafetyEvidence(
        allowed=allowed,
        authority=highest.authority,
        reason=";".join(item.reason for item in evidence),
        source="+".join(item.source for item in evidence),
        timestamp=max(item.timestamp for item in evidence),
        evidence_refs=tuple(ref for item in evidence for ref in item.evidence_refs),
        severity="critical" if highest.authority is DiagnosticAuthority.HARD_STOP else ("error" if not allowed else "info"),
        confidence=min(item.confidence for item in evidence),
    )
