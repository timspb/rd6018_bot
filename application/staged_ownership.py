"""Declarative V2 -> V3 ownership cutover model; no runtime mutation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class OwnershipStage(str, Enum):
    STAGE_0_SHADOW = "stage_0_shadow"
    STAGE_1_DECISION = "stage_1_decision"
    STAGE_2_EXECUTION_STAGED = "stage_2_execution_staged"
    STAGE_3_FULL = "stage_3_full"


@dataclass(frozen=True)
class OwnershipSnapshot:
    decision_owner: str
    execution_owner: str
    physical_owner: str
    lease_owner: str
    configuration_owner: str
    telemetry_owner: str


@dataclass(frozen=True)
class CutoverResult:
    accepted: bool
    stage: OwnershipStage
    ownership: OwnershipSnapshot
    missing_gates: tuple[str, ...] = ()
    abort_conditions: tuple[str, ...] = ()


class StagedOwnershipCutoverModel:
    """Validate a proposed stage using evidence, without changing live ownership."""

    _ORDER = (
        OwnershipStage.STAGE_0_SHADOW,
        OwnershipStage.STAGE_1_DECISION,
        OwnershipStage.STAGE_2_EXECUTION_STAGED,
        OwnershipStage.STAGE_3_FULL,
    )

    def __init__(self) -> None:
        self._stage = OwnershipStage.STAGE_0_SHADOW
        self._ownership = self._ownership_for(self._stage)

    @property
    def stage(self) -> OwnershipStage:
        return self._stage

    @property
    def ownership(self) -> OwnershipSnapshot:
        return self._ownership

    def transition(self, target: OwnershipStage, evidence: Mapping[str, bool]) -> CutoverResult:
        if not isinstance(target, OwnershipStage):
            target = OwnershipStage(target)
        current_index = self._ORDER.index(self._stage)
        target_index = self._ORDER.index(target)
        if target_index != current_index + 1:
            return CutoverResult(False, self._stage, self._ownership, ("sequential_transition_required",))
        missing = tuple(gate for gate in self._gates(target) if not bool(evidence.get(gate, False)))
        proposed = self._ownership_for(target)
        aborts = self._conflicts(proposed)
        if missing or aborts:
            return CutoverResult(False, self._stage, self._ownership, missing, aborts)
        self._stage = target
        self._ownership = proposed
        return CutoverResult(True, self._stage, self._ownership)

    def rollback(self, evidence: Mapping[str, bool]) -> CutoverResult:
        required = ("v2_healthy", "rollback_verified", "no_ambiguous_session")
        missing = tuple(gate for gate in required if not bool(evidence.get(gate, False)))
        if missing:
            return CutoverResult(False, self._stage, self._ownership, missing)
        self._stage = OwnershipStage.STAGE_0_SHADOW
        self._ownership = self._ownership_for(self._stage)
        return CutoverResult(True, self._stage, self._ownership)

    @classmethod
    def validate_ownership(cls, ownership: OwnershipSnapshot) -> tuple[str, ...]:
        return cls._conflicts(ownership)

    @classmethod
    def _conflicts(cls, ownership: OwnershipSnapshot) -> tuple[str, ...]:
        conflicts: list[str] = []
        if ownership.physical_owner not in {"V2", "V3"}:
            conflicts.append("invalid_physical_owner")
        if ownership.lease_owner not in {"V2", "V3"}:
            conflicts.append("invalid_lease_owner")
        if ownership.configuration_owner not in {"V2", "V3"}:
            conflicts.append("invalid_configuration_owner")
        if ownership.telemetry_owner not in {"V2", "V3"}:
            conflicts.append("invalid_telemetry_owner")
        return tuple(conflicts)

    @staticmethod
    def _gates(stage: OwnershipStage) -> tuple[str, ...]:
        common = ("v2_healthy", "v3_healthy", "long_run_pass", "rollback_ready", "no_unexplained_conflicts")
        if stage is OwnershipStage.STAGE_1_DECISION:
            return common + ("decision_approval",)
        if stage is OwnershipStage.STAGE_2_EXECUTION_STAGED:
            return common + ("decision_approval", "execution_shadow_pass", "execution_approval")
        if stage is OwnershipStage.STAGE_3_FULL:
            return common + ("decision_approval", "execution_shadow_pass", "execution_approval", "physical_bench_pass", "full_cutover_approval")
        return ()

    @staticmethod
    def _ownership_for(stage: OwnershipStage) -> OwnershipSnapshot:
        if stage is OwnershipStage.STAGE_0_SHADOW:
            return OwnershipSnapshot("V2", "V2", "V2", "V2", "V3", "V3")
        if stage is OwnershipStage.STAGE_1_DECISION:
            return OwnershipSnapshot("V3", "V2", "V2", "V2", "V3", "V3")
        if stage is OwnershipStage.STAGE_2_EXECUTION_STAGED:
            return OwnershipSnapshot("V3", "V3-boundary", "V2", "V2", "V3", "V3")
        return OwnershipSnapshot("V3", "V3", "V3", "V3", "V3", "V3")


__all__ = ["OwnershipStage", "OwnershipSnapshot", "CutoverResult", "StagedOwnershipCutoverModel"]
