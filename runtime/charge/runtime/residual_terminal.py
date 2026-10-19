"""Terminal-stage flow decision for the residual runtime observer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResidualTerminalDecision:
    stage: str
    return_after_observation: bool


def decide_residual_terminal(stage: str, *, idle_stage: str, done_stage: str) -> ResidualTerminalDecision:
    """Preserve IDLE's early return and DONE's post-observation return point."""
    if stage not in {idle_stage, done_stage}:
        raise ValueError(f"unsupported terminal residual stage: {stage}")
    return ResidualTerminalDecision(stage=stage, return_after_observation=stage == idle_stage)


__all__ = ["ResidualTerminalDecision", "decide_residual_terminal"]
