"""Manual MIX delta evidence transform over explicit state, policy and sample."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Optional


MANUAL_DELTA_BLANKING_SEC = 120.0
MANUAL_DELTA_CONFIRM_COUNT = 3
MANUAL_DELTA_CONFIRM_INTERVAL_SEC = 60.0

logger = logging.getLogger("rd6018.manual")


@dataclass(frozen=True)
class ManualDeltaSample:
    """Telemetry-normalized input supplied by the Application observer."""

    mode: str
    voltage_v: Optional[float]
    current_a: Optional[float]


@dataclass(frozen=True)
class ManualDeltaEvidenceState:
    """Immutable snapshot of the four ManualSessionManager-owned evidence fields."""

    imin: Optional[float] = None
    vmax: Optional[float] = None
    confirmations: int = 0
    last_confirmation_at: float = 0.0


@dataclass(frozen=True)
class ManualDeltaEvidencePolicy:
    """Existing request/profile policy values; this module does not derive them."""

    delta_current_a: Optional[float]
    delta_voltage_v: Optional[float]
    confirmation_count: int = MANUAL_DELTA_CONFIRM_COUNT
    confirmation_interval_seconds: float = MANUAL_DELTA_CONFIRM_INTERVAL_SEC
    blanking_seconds: float = MANUAL_DELTA_BLANKING_SEC


@dataclass(frozen=True)
class ManualDeltaEvidenceResult:
    state: ManualDeltaEvidenceState
    reason: Optional[str] = None


def evaluate_manual_delta_evidence(
    state: ManualDeltaEvidenceState,
    policy: ManualDeltaEvidencePolicy,
    sample: ManualDeltaSample,
    *,
    started_at: float,
    now: float,
) -> ManualDeltaEvidenceResult:
    """Return the next Manual Delta evidence state without mutating its owner."""
    threshold = (
        policy.delta_current_a if sample.mode == "cv" else policy.delta_voltage_v
    )
    if threshold is None or now - started_at < policy.blanking_seconds:
        return ManualDeltaEvidenceResult(state=state)

    voltage = sample.voltage_v
    current = sample.current_a
    if voltage is None or current is None:
        return ManualDeltaEvidenceResult(state=state)

    next_state = state
    candidate = False
    if sample.mode == "cv":
        if state.imin is None or current < state.imin:
            next_state = replace(
                state,
                imin=current,
                confirmations=0,
                last_confirmation_at=0.0,
            )
            logger.info(
                "MANUAL_EVIDENCE kind=minimum event=update mode=CV value=%.3f timestamp=%.3f",
                current,
                now,
            )
        elif current >= state.imin + threshold:
            candidate = True
    elif sample.mode == "cc":
        if state.vmax is None or voltage > state.vmax:
            next_state = replace(
                state,
                vmax=voltage,
                confirmations=0,
                last_confirmation_at=0.0,
            )
            logger.info(
                "MANUAL_EVIDENCE kind=maximum event=update mode=CC value=%.3f timestamp=%.3f",
                voltage,
                now,
            )
        elif voltage <= state.vmax - threshold:
            candidate = True
    else:
        return ManualDeltaEvidenceResult(
            state=replace(state, confirmations=0)
        )

    if not candidate:
        return ManualDeltaEvidenceResult(
            state=replace(next_state, confirmations=0)
        )
    if (
        next_state.last_confirmation_at
        and now - next_state.last_confirmation_at < policy.confirmation_interval_seconds
    ):
        return ManualDeltaEvidenceResult(state=next_state)

    confirmed_state = replace(
        next_state,
        last_confirmation_at=now,
        confirmations=next_state.confirmations + 1,
    )
    logger.info(
        "MANUAL_EVIDENCE kind=delta event=confirmation mode=%s count=%d reference=%.3f threshold=%.3f timestamp=%.3f",
        sample.mode,
        confirmed_state.confirmations,
        confirmed_state.imin if sample.mode == "cv" else confirmed_state.vmax,
        threshold,
        now,
    )
    reason = (
        "manual_delta_confirmed"
        if confirmed_state.confirmations >= policy.confirmation_count
        else None
    )
    return ManualDeltaEvidenceResult(state=confirmed_state, reason=reason)


__all__ = [
    "MANUAL_DELTA_BLANKING_SEC",
    "MANUAL_DELTA_CONFIRM_COUNT",
    "MANUAL_DELTA_CONFIRM_INTERVAL_SEC",
    "ManualDeltaEvidencePolicy",
    "ManualDeltaEvidenceResult",
    "ManualDeltaEvidenceState",
    "ManualDeltaSample",
    "evaluate_manual_delta_evidence",
]
