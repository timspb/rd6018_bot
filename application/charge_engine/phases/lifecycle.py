"""Generic lifecycle registry and data-only canonical phase contracts."""

from __future__ import annotations

from typing import Iterable, Mapping

from .contracts import (
    CanonicalPhase, DeltaPolicy, HoldPolicy, InterruptionPolicy, PhaseContract,
    PhaseEvaluation, PhaseStatus, RecoveryPolicy, TimeoutPolicy,
)


class PhaseLifecycleRegistry:
    def __init__(self, contracts: Iterable[PhaseContract]) -> None:
        values = tuple(contracts)
        ids = tuple(contract.phase_id for contract in values)
        if len(ids) != len(set(ids)):
            raise ValueError("phase contract ids must be unique")
        self._contracts = {contract.phase_id: contract for contract in values}

    def get(self, phase_id: str) -> PhaseContract:
        try:
            return self._contracts[str(phase_id)]
        except KeyError as exc:
            raise KeyError(f"unknown phase contract: {phase_id}") from exc

    def ids(self) -> tuple[str, ...]:
        return tuple(self._contracts)


def canonical_phase_contracts() -> tuple[PhaseContract, ...]:
    """Return generic lifecycle contracts; targets and chemistry stay external."""
    return (
        PhaseContract("PREP", ("preparation_requested",), ("preparation_complete",), ("fresh_telemetry",), TimeoutPolicy.INTERRUPT, None, InterruptionPolicy.SAFE_WAIT, RecoveryPolicy.RECHECK_ENTRY),
        PhaseContract("MAIN", ("main_requested",), ("main_complete",), ("phase_evidence_confirmed",), TimeoutPolicy.REPORT, None, InterruptionPolicy.PAUSE, RecoveryPolicy.RESUME),
        PhaseContract("DESULFATION", ("desulfation_requested",), ("desulfation_complete",), ("program_confirmation",), TimeoutPolicy.INTERRUPT, None, InterruptionPolicy.SAFE_WAIT, RecoveryPolicy.RESTART_PHASE),
        PhaseContract("MIX", ("mix_requested",), ("delta_complete",), ("delta_confirmation",), TimeoutPolicy.INTERRUPT, None, InterruptionPolicy.SAFE_WAIT, RecoveryPolicy.RECHECK_ENTRY, delta_policy=DeltaPolicy("mix_active", "confirmed_delta", None, ("voltage", "current", "temperature"), "program-defined delta evidence")),
        PhaseContract("HOLD", ("hold_requested",), ("hold_complete",), ("continuous_hold_evidence",), TimeoutPolicy.INTERRUPT, None, InterruptionPolicy.PAUSE, RecoveryPolicy.RESUME, hold_policy=HoldPolicy("delta_complete", None, "hold_duration_elapsed", InterruptionPolicy.PAUSE, "program-defined finish hold")),
        PhaseContract("SAFE_WAIT", ("containment_requested",), ("safe_wait_complete",), ("off_verification",), TimeoutPolicy.INTERRUPT, None, InterruptionPolicy.ABORT, RecoveryPolicy.RECHECK_ENTRY),
        PhaseContract("DONE", ("completion_requested",), ("terminal_state",), ("completion_evidence",), TimeoutPolicy.NONE, None, InterruptionPolicy.NONE, RecoveryPolicy.NONE),
    )


__all__ = ["PhaseLifecycleRegistry", "canonical_phase_contracts"]
