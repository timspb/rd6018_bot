"""Non-activating V3 canary readiness and migration gate contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class ReadinessStatus(str, Enum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    NOT_VALIDATED = "NOT_VALIDATED"


class GateSection(str, Enum):
    ARCHITECTURE = "Architecture"
    DOMAIN = "Domain"
    SAFETY = "Safety"
    EXECUTION = "Execution"
    EXTERNAL = "External"
    OBSERVABILITY = "Observability"


@dataclass(frozen=True)
class ReadinessItem:
    section: GateSection
    name: str
    status: ReadinessStatus
    evidence: str
    blocker: str | None
    owner: str


@dataclass(frozen=True)
class V3CanaryReadinessMatrix:
    items: tuple[ReadinessItem, ...]

    @property
    def blockers(self) -> tuple[ReadinessItem, ...]:
        return tuple(item for item in self.items if item.status is ReadinessStatus.BLOCKED)

    @property
    def status(self) -> ReadinessStatus:
        if self.blockers:
            return ReadinessStatus.BLOCKED
        if any(item.status in {ReadinessStatus.PARTIAL, ReadinessStatus.NOT_VALIDATED} for item in self.items):
            return ReadinessStatus.PARTIAL
        return ReadinessStatus.PASS


def default_readiness_matrix() -> V3CanaryReadinessMatrix:
    rows = (
        (GateSection.ARCHITECTURE, "dependency isolation", ReadinessStatus.PASS, "architecture guardrail tests", None, "V3 composition"),
        (GateSection.ARCHITECTURE, "legacy separation", ReadinessStatus.PARTIAL, "R4 audit and V3 core checks", "full standalone production cutover not proven", "V3 architecture"),
        (GateSection.DOMAIN, "FSM/profile/strategy/session", ReadinessStatus.PARTIAL, "domain parity and shadow tests", "unresolved parity decisions remain", "V3 domain"),
        (GateSection.DOMAIN, "canonical events", ReadinessStatus.PASS, "canonical event tests", None, "V3 timeline"),
        (GateSection.SAFETY, "ownership/containment/lease", ReadinessStatus.PARTIAL, "lease and safety contracts", "live ownership transfer and full bench proof absent", "V2/edge safety"),
        (GateSection.EXECUTION, "adapter/readback/rollback", ReadinessStatus.PARTIAL, "bench adapter tests", "real physical readback validation absent", "V2 execution"),
        (GateSection.EXTERNAL, "HA/ESPHome/RD parity", ReadinessStatus.BLOCKED, "HA snapshot only; direct parity incomplete", "external parity and target-node validation incomplete", "external adapters"),
        (GateSection.OBSERVABILITY, "diagnostics/timeline/evidence", ReadinessStatus.PARTIAL, "shadow evidence and live HA evidence", "V3 observer trace and complete session evidence absent", "V3 observability"),
    )
    return V3CanaryReadinessMatrix(tuple(ReadinessItem(*row) for row in rows))


@dataclass(frozen=True)
class CanaryEntryCriteria:
    architecture: bool
    safety: bool
    execution: bool
    operational: bool
    external: bool
    required_evidence: tuple[str, ...] = ()

    @property
    def satisfied(self) -> bool:
        return all((self.architecture, self.safety, self.execution, self.operational, self.external))


class CanaryMode(str, Enum):
    SHADOW_ONLY = "MODE_0_SHADOW_ONLY"
    DECISION_SHADOW = "MODE_1_DECISION_SHADOW"
    CANARY_DECISION = "MODE_2_CANARY_DECISION_OWNERSHIP"
    FULL_OWNERSHIP = "MODE_3_FULL_OWNERSHIP"


@dataclass(frozen=True)
class CanaryModeDefinition:
    mode: CanaryMode
    v2_role: str
    v3_role: str
    entry: str
    exit: str
    rollback: str


def canary_modes() -> tuple[CanaryModeDefinition, ...]:
    return (
        CanaryModeDefinition(CanaryMode.SHADOW_ONLY, "owner", "observe", "none beyond observation safety", "explicit stop", "retain V2"),
        CanaryModeDefinition(CanaryMode.DECISION_SHADOW, "execution owner", "calculates only", "shadow acceptance PASS", "revoke shadow", "return to V2 decisions"),
        CanaryModeDefinition(CanaryMode.CANARY_DECISION, "execution owner", "limited decision authority", "explicit approval and all gates", "expiry or revoke", "return decision to V2"),
        CanaryModeDefinition(CanaryMode.FULL_OWNERSHIP, "compatibility reference", "complete owner", "separate migration approval", "explicit rollback", "restore last safe owner"),
    )


class RollbackTrigger(str, Enum):
    SAFETY_DIVERGENCE = "safety_divergence"
    EXECUTION_MISMATCH = "execution_mismatch"
    TELEMETRY_CONFLICT = "telemetry_conflict"
    LEASE_FAILURE = "lease_failure"
    UNKNOWN_STATE = "unknown_state"
    HEALTH_DEGRADATION = "health_degradation"


@dataclass(frozen=True)
class CanaryRollbackModel:
    triggers: tuple[RollbackTrigger, ...]
    actions: tuple[str, ...] = ("revoke authority", "return ownership", "preserve evidence", "notify operator")

    def requires_rollback(self, trigger: RollbackTrigger) -> bool:
        return trigger in self.triggers


@dataclass(frozen=True)
class CanaryApprovalGate:
    approval_owner: str | None
    required_evidence: tuple[str, ...]
    approved_at: float | None = None
    expires_at: float | None = None
    revoked: bool = False
    revoke_condition: str = "any rollback trigger or expiry"

    @property
    def approved(self) -> bool:
        return bool(self.approval_owner and self.approved_at and self.expires_at and not self.revoked)

    def revoke(self) -> "CanaryApprovalGate":
        return CanaryApprovalGate(self.approval_owner, self.required_evidence, self.approved_at, self.expires_at, True, self.revoke_condition)


class BlockerType(str, Enum):
    ARCHITECTURE = "TYPE_A_ARCHITECTURE"
    SAFETY = "TYPE_B_SAFETY"
    VALIDATION = "TYPE_C_VALIDATION"
    OPERATIONAL = "TYPE_D_OPERATIONAL"
    LIMITATION = "TYPE_E_KNOWN_LIMITATION"


@dataclass(frozen=True)
class ReadinessBlocker:
    blocker_type: BlockerType
    description: str
    impact: str
    resolution_path: str


__all__ = ["ReadinessStatus", "GateSection", "ReadinessItem", "V3CanaryReadinessMatrix", "default_readiness_matrix", "CanaryEntryCriteria", "CanaryMode", "CanaryModeDefinition", "canary_modes", "RollbackTrigger", "CanaryRollbackModel", "CanaryApprovalGate", "BlockerType", "ReadinessBlocker"]
