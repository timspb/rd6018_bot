"""Declarative V2 -> V3 ownership transition model for Phase 10.3."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class AuthorityOwner(str, Enum):
    V2 = "V2"
    V3 = "V3"
    SHARED = "shared"


class MigrationMode(str, Enum):
    MIRROR = "mirror"
    SHADOW = "shadow"
    STAGED = "staged"
    CUTOVER = "cutover"
    ROLLBACK = "rollback"


class TransitionComponent(str, Enum):
    UI = "UI"
    TELEMETRY = "telemetry"
    CONFIGURATION = "configuration"
    DIAGNOSTICS = "diagnostics"
    PERSISTENCE = "persistence"
    DOMAIN_DECISIONS = "domain decisions"
    SAFETY_DECISIONS = "safety decisions"
    EXECUTION = "execution"
    HA_CONTROL = "HA control"
    ESP_CONTROL = "ESP control"
    PHYSICAL_OUTPUT = "physical output"


@dataclass(frozen=True)
class AuthorityMatrixEntry:
    component: TransitionComponent
    current_owner: AuthorityOwner
    target_owner: AuthorityOwner
    migration_mode: MigrationMode
    rollback_conditions: tuple[str, ...]
    approval_gate: str


@dataclass(frozen=True)
class OwnershipTransitionPlan:
    matrix: tuple[AuthorityMatrixEntry, ...]
    rollback_conditions: tuple[str, ...]
    dual_run_rules: tuple[str, ...]
    approval_gates: tuple[str, ...]
    ownership_transfer_enabled: bool = False

    def __post_init__(self) -> None:
        expected = set(TransitionComponent)
        actual = {entry.component for entry in self.matrix}
        if actual != expected:
            missing = ", ".join(item.value for item in sorted(expected - actual, key=lambda item: item.value))
            extra = ", ".join(item.value for item in sorted(actual - expected, key=lambda item: item.value))
            raise ValueError(f"authority matrix incomplete; missing={missing}; extra={extra}")
        if self.ownership_transfer_enabled:
            raise ValueError("Phase 10.3 model cannot enable ownership transfer")
        if not self.rollback_conditions or not self.dual_run_rules or not self.approval_gates:
            raise ValueError("rollback, dual-run and approval rules are required")
        for entry in self.matrix:
            if entry.target_owner is not AuthorityOwner.V3:
                raise ValueError(f"target owner must be V3: {entry.component.value}")
            if not entry.rollback_conditions or not entry.approval_gate.strip():
                raise ValueError(f"rollback and approval gate required: {entry.component.value}")

    def entry(self, component: TransitionComponent) -> AuthorityMatrixEntry:
        return next(item for item in self.matrix if item.component is component)


def default_transition_plan() -> OwnershipTransitionPlan:
    common_rollback = (
        "unexpected conflict exceeds accepted threshold",
        "safety or containment divergence is observed",
        "trace/evidence continuity is lost",
    )
    gates = {
        TransitionComponent.UI: "UI parity and operator rollback confirmed",
        TransitionComponent.TELEMETRY: "ESP/HA arbitration stable with freshness evidence",
        TransitionComponent.CONFIGURATION: "no unresolved or conflicting authority values",
        TransitionComponent.DIAGNOSTICS: "complete correlated evidence available",
        TransitionComponent.PERSISTENCE: "restore candidates remain non-authorizing",
        TransitionComponent.DOMAIN_DECISIONS: "shadow acceptance criteria passed",
        TransitionComponent.SAFETY_DECISIONS: "zero unexplained safety/containment conflicts",
        TransitionComponent.EXECUTION: "intent parity and rollback verification passed",
        TransitionComponent.HA_CONTROL: "explicit separate control cutover approval",
        TransitionComponent.ESP_CONTROL: "ESP contract and bench gate approved",
        TransitionComponent.PHYSICAL_OUTPUT: "physical bench and emergency rollback approval",
    }
    modes = {
        TransitionComponent.UI: MigrationMode.STAGED,
        TransitionComponent.TELEMETRY: MigrationMode.MIRROR,
        TransitionComponent.CONFIGURATION: MigrationMode.SHADOW,
        TransitionComponent.DIAGNOSTICS: MigrationMode.MIRROR,
        TransitionComponent.PERSISTENCE: MigrationMode.SHADOW,
        TransitionComponent.DOMAIN_DECISIONS: MigrationMode.SHADOW,
        TransitionComponent.SAFETY_DECISIONS: MigrationMode.SHADOW,
        TransitionComponent.EXECUTION: MigrationMode.SHADOW,
        TransitionComponent.HA_CONTROL: MigrationMode.CUTOVER,
        TransitionComponent.ESP_CONTROL: MigrationMode.CUTOVER,
        TransitionComponent.PHYSICAL_OUTPUT: MigrationMode.CUTOVER,
    }
    current = {
        TransitionComponent.UI: AuthorityOwner.V2,
        TransitionComponent.TELEMETRY: AuthorityOwner.SHARED,
        TransitionComponent.CONFIGURATION: AuthorityOwner.SHARED,
        TransitionComponent.DIAGNOSTICS: AuthorityOwner.SHARED,
        TransitionComponent.PERSISTENCE: AuthorityOwner.V2,
        TransitionComponent.DOMAIN_DECISIONS: AuthorityOwner.V2,
        TransitionComponent.SAFETY_DECISIONS: AuthorityOwner.V2,
        TransitionComponent.EXECUTION: AuthorityOwner.V2,
        TransitionComponent.HA_CONTROL: AuthorityOwner.V2,
        TransitionComponent.ESP_CONTROL: AuthorityOwner.V2,
        TransitionComponent.PHYSICAL_OUTPUT: AuthorityOwner.V2,
    }
    matrix = tuple(
        AuthorityMatrixEntry(component, current[component], AuthorityOwner.V3, modes[component], common_rollback, gates[component])
        for component in TransitionComponent
    )
    return OwnershipTransitionPlan(
        matrix=matrix,
        rollback_conditions=common_rollback,
        dual_run_rules=(
            "V2 remains active owner during mirror/shadow/staged modes",
            "V3 output is observational and cannot execute an ActuatorIntent",
            "conflicts are recorded and never resolved by implicit precedence",
        ),
        approval_gates=(
            "shadow acceptance criteria passed",
            "safety and containment parity explicitly approved",
            "operator and physical bench approval obtained before control cutover",
        ),
    )


__all__ = [
    "AuthorityOwner", "MigrationMode", "TransitionComponent",
    "AuthorityMatrixEntry", "OwnershipTransitionPlan", "default_transition_plan",
]
