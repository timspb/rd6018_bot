"""Read-only Canary blocker inventory and resolution planning contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class BlockerCategory(str, Enum):
    ARCHITECTURE = "Architecture"
    SAFETY = "Safety"
    EXECUTION = "Execution"
    EXTERNAL = "External"
    OPERATIONAL = "Operational"
    APPROVAL = "Approval"


class BlockerStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class CanaryBlocker:
    id: str
    category: BlockerCategory
    description: str
    source: str
    impact: str
    owner: str
    required_evidence: tuple[str, ...]
    resolution_criteria: tuple[str, ...]
    status: BlockerStatus = BlockerStatus.OPEN


class CanaryBlockerRegistry:
    """Immutable-style registry: registration returns a new registry."""

    def __init__(self, blockers: tuple[CanaryBlocker, ...] = ()) -> None:
        self._blockers = tuple(blockers)

    @property
    def blockers(self) -> tuple[CanaryBlocker, ...]:
        return self._blockers

    @property
    def active(self) -> tuple[CanaryBlocker, ...]:
        return tuple(item for item in self._blockers if item.status is not BlockerStatus.RESOLVED)

    def register(self, blocker: CanaryBlocker) -> "CanaryBlockerRegistry":
        if any(item.id == blocker.id for item in self._blockers):
            raise ValueError(f"duplicate blocker id: {blocker.id}")
        if not blocker.required_evidence or not blocker.resolution_criteria:
            raise ValueError("blocker requires evidence and resolution criteria")
        return CanaryBlockerRegistry(self._blockers + (blocker,))

    def by_category(self, category: BlockerCategory) -> tuple[CanaryBlocker, ...]:
        return tuple(item for item in self._blockers if item.category is category)


@dataclass(frozen=True)
class ApprovalResolutionModel:
    owner: str
    required_evidence: tuple[str, ...]
    validity_window_s: int
    revoke_conditions: tuple[str, ...]
    creation_allowed: bool = False


@dataclass(frozen=True)
class ExternalValidationGap:
    system: str
    proven: tuple[str, ...]
    missing: tuple[str, ...]
    pass_criteria: tuple[str, ...]
    status: BlockerStatus = BlockerStatus.OPEN


@dataclass(frozen=True)
class CanaryBlockerResolutionPlan:
    priority: int
    blocker_id: str
    action: str
    risk: str
    validation_method: str
    rollback: str


@dataclass(frozen=True)
class CanaryBlockerSnapshot:
    active_blockers: tuple[str, ...]
    progress: Mapping[str, str]
    evidence_state: Mapping[str, Any]


def live_evaluation_blockers() -> CanaryBlockerRegistry:
    """The blockers observed in Workstream 18, without granting approval."""
    registry = CanaryBlockerRegistry()
    for blocker in (
        CanaryBlocker(
            "CB-APPROVAL-001", BlockerCategory.APPROVAL,
            "No explicit Canary approval with owner, scope and expiry.",
            "RD6018_CANARY_PREFLIGHT_LIVE_EVALUATION_REPORT.md", "Canary gate cannot be authorized.",
            "designated operator/approver", ("approved evidence package", "scope", "expiry", "revoke authority"),
            ("approval record exists", "owner and scope are explicit", "expiry is in the future", "revoke path is recorded"),
        ),
        CanaryBlocker(
            "CB-SAFETY-LEASE-001", BlockerCategory.SAFETY,
            "Lease safety indicators are stale and do not prove an unambiguous current state.",
            "RD6018_CANARY_PREFLIGHT_LIVE_EVALUATION_REPORT.md", "Unknown safety state blocks Canary.",
            "V2/edge safety owner", ("fresh armed/tripped/quarantine timestamps", "current lease owner", "fresh expiry/renewal observation"),
            ("all safety indicators are fresh", "no conflicting lease state", "ownership remains unchanged"),
        ),
        CanaryBlocker(
            "CB-EXTERNAL-001", BlockerCategory.EXTERNAL,
            "ESPHome direct and independent RD parity are not fully validated.",
            "RD6018_CANARY_PREFLIGHT_LIVE_EVALUATION_REPORT.md", "External source disagreement or stale readback could invalidate decisions.",
            "external integration owner", ("ESP telemetry mapping", "RD readback", "freshness", "verification parity"),
            ("HA/ESP/RD observations agree", "freshness thresholds pass", "readback verification is evidenced"),
        ),
        CanaryBlocker(
            "CB-EVIDENCE-001", BlockerCategory.OPERATIONAL,
            "A complete fresh V3 shadow evidence chain is not available.",
            "RD6018_CANARY_PREFLIGHT_LIVE_EVALUATION_REPORT.md", "V3 behavior cannot be independently replayed and correlated.",
            "V3 observability owner", ("session id", "trace continuity", "START/phases/Delta/Hold/termination/STOP", "telemetry and diagnostics"),
            ("all required events are present", "timestamps are ordered", "session and trace IDs are continuous", "replay has no unknown safety state"),
        ),
        CanaryBlocker(
            "CB-READINESS-001", BlockerCategory.EXECUTION,
            "Readiness matrix still contains safety, execution, external and observability limitations.",
            "RD6018_V3_CANARY_READINESS_MODEL.md", "Canary entry criteria remain unsatisfied.",
            "V3 migration gate owner", ("updated readiness matrix", "bench/readback evidence", "rollback evidence"),
            ("all critical matrix items PASS", "no unresolved safety/ownership blocker", "rollback is tested and documented"),
        ),
    ):
        registry = registry.register(blocker)
    return registry


__all__ = ["BlockerCategory", "BlockerStatus", "CanaryBlocker", "CanaryBlockerRegistry", "ApprovalResolutionModel", "ExternalValidationGap", "CanaryBlockerResolutionPlan", "CanaryBlockerSnapshot", "live_evaluation_blockers"]
