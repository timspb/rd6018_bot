"""Bench observation comparison with a command plan; no hardware execution."""

from __future__ import annotations

from dataclasses import dataclass

from .command_plan import PhysicalCommandPlan


@dataclass(frozen=True)
class BenchObservation:
    completed_steps: tuple[str, ...]
    output_state: bool | None = None
    readback_valid: bool = False
    notes: str = ""


@dataclass(frozen=True)
class BenchShadowResult:
    status: str
    missing_steps: tuple[str, ...]
    unexpected_steps: tuple[str, ...]
    output_state: bool | None
    readback_valid: bool


class BenchExecutionShadow:
    """Compare externally supplied observations to a plan without executing it."""

    def compare(self, plan: PhysicalCommandPlan, observation: BenchObservation) -> BenchShadowResult:
        expected = tuple(step.name for step in plan.steps)
        completed = observation.completed_steps
        missing = tuple(step for step in expected if step not in completed)
        unexpected = tuple(step for step in completed if step not in expected)
        return BenchShadowResult(
            "MATCH" if not missing and not unexpected and observation.readback_valid else "MISMATCH",
            missing, unexpected, observation.output_state, observation.readback_valid,
        )
