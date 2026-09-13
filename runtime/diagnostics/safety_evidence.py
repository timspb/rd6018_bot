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

    def __post_init__(self) -> None:
        if not self.reason.strip() or not self.source.strip():
            raise ValueError("safety evidence reason and source are required")


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
    )


def evaluate_safety_evidence(evidence: SafetyEvidence) -> bool:
    """Shadow-only gate result; no OutputIntent is created."""
    return evidence.allowed and evidence.authority is DiagnosticAuthority.ALLOW
