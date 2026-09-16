"""Pure V2/V3 decision-authority coordination; no execution integration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .v2_v3_comparison import ComparisonContext, ComparisonResult, DecisionSnapshot, V2V3ComparisonEngine


class DecisionAuthorityMode(str, Enum):
    SHADOW = "shadow"
    ADVISORY = "advisory"
    STAGED = "staged"
    ACTIVE_DECISION = "active_decision"


class DecisionOwner(str, Enum):
    V2 = "V2"
    V3 = "V3"


@dataclass(frozen=True)
class DecisionProvenance:
    trace_id: str
    source: str
    authority: DecisionOwner
    mode: DecisionAuthorityMode
    comparison_status: str
    reason: str


@dataclass(frozen=True)
class DecisionAuthorityResult:
    trace_id: str
    owner: DecisionOwner
    mode: DecisionAuthorityMode
    selected: DecisionSnapshot | None
    v2: DecisionSnapshot | None
    v3: DecisionSnapshot | None
    comparison: ComparisonResult
    provenance: DecisionProvenance


class DecisionAuthorityCoordinator:
    """Compare decisions and prevent implicit V2 -> V3 takeover."""

    def __init__(self, *, expected_differences: set[str] | frozenset[str] = frozenset()) -> None:
        self._mode = DecisionAuthorityMode.SHADOW
        self._owner = DecisionOwner.V2
        self._expected_differences = frozenset(expected_differences)
        self._provenance: list[DecisionProvenance] = []

    @property
    def mode(self) -> DecisionAuthorityMode:
        return self._mode

    @property
    def owner(self) -> DecisionOwner:
        return self._owner

    @property
    def provenance(self) -> tuple[DecisionProvenance, ...]:
        return tuple(self._provenance)

    def set_mode(self, mode: DecisionAuthorityMode, *, explicit_approval: bool = False) -> None:
        if not isinstance(mode, DecisionAuthorityMode):
            mode = DecisionAuthorityMode(mode)
        if mode in {DecisionAuthorityMode.STAGED, DecisionAuthorityMode.ACTIVE_DECISION} and not explicit_approval:
            raise PermissionError("explicit decision-authority approval is required")
        self._mode = mode
        self._owner = DecisionOwner.V2 if mode in {DecisionAuthorityMode.SHADOW, DecisionAuthorityMode.ADVISORY} else DecisionOwner.V3

    def evaluate(
        self,
        context: ComparisonContext,
        v2: DecisionSnapshot | None,
        v3: DecisionSnapshot | None,
    ) -> DecisionAuthorityResult:
        comparison = V2V3ComparisonEngine(
            lambda _context: v2,
            lambda _context: v3,
            expected_differences=self._expected_differences,
        ).compare(context)
        selected = v2 if self._owner is DecisionOwner.V2 else v3
        reason = "v2_authoritative_shadow_compare" if self._owner is DecisionOwner.V2 else "v3_authority_explicitly_approved"
        if self._owner is DecisionOwner.V3 and v3 is None:
            selected = None
            reason = "v3_decision_missing_no_implicit_v2_takeover"
        provenance = DecisionProvenance(
            trace_id=context.trace_id,
            source="decision-authority-coordinator",
            authority=self._owner,
            mode=self._mode,
            comparison_status=comparison.status.value,
            reason=reason,
        )
        self._provenance.append(provenance)
        return DecisionAuthorityResult(context.trace_id, self._owner, self._mode, selected, v2, v3, comparison, provenance)

    def rollback_to_v2(self, *, reason: str = "explicit_v2_rollback") -> DecisionProvenance:
        self._mode = DecisionAuthorityMode.SHADOW
        self._owner = DecisionOwner.V2
        provenance = DecisionProvenance("rollback", "decision-authority-coordinator", DecisionOwner.V2, self._mode, "not_compared", reason)
        self._provenance.append(provenance)
        return provenance


__all__ = [
    "DecisionAuthorityMode", "DecisionOwner", "DecisionProvenance",
    "DecisionAuthorityResult", "DecisionAuthorityCoordinator",
]
