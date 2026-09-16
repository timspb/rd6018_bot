"""Gated handoff boundary for a future V3 START execution migration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from .runtime_start_service import RuntimeStartService, StartExecutionTrace
from .start_dry_run import StartDryRunIntegrationGate, StartDryRunReport
from .start_plan import ApprovedStartPlan


class StartExecutionMode(str, Enum):
    SHADOW = "shadow"
    DRY_RUN = "dry_run"
    ACTIVE = "active"


@dataclass(frozen=True)
class StartHandoffPlan:
    profile: str
    chemistry: str
    recipe_id: str
    target_voltage_v: float
    target_current_a: float
    mode: StartExecutionMode
    controller_handoff: str
    physical_execution: bool = False


@dataclass(frozen=True)
class StartAdapterResult:
    accepted: bool
    mode: StartExecutionMode
    reason: str
    trace: StartExecutionTrace | None = None
    handoff_plan: StartHandoffPlan | None = None


class StartExecutionAdapter:
    """Bridge only; it has no controller, HA, or physical dependency."""

    def __init__(
        self,
        runtime_start_service: RuntimeStartService | None = None,
        *,
        active_enabled: bool = False,
        active_handoff: Callable[[ApprovedStartPlan], Any] | None = None,
    ) -> None:
        self.runtime_start_service = runtime_start_service or RuntimeStartService()
        self.active_enabled = bool(active_enabled)
        self.active_handoff = active_handoff

    def execute(
        self,
        plan: ApprovedStartPlan,
        mode: StartExecutionMode = StartExecutionMode.SHADOW,
    ) -> StartAdapterResult:
        """Validate and describe a handoff; never performs physical execution by default."""
        if mode is StartExecutionMode.ACTIVE:
            return self._active(plan)

        trace = self.runtime_start_service.build_trace(plan)
        if not trace.allowed:
            return StartAdapterResult(False, mode, ", ".join(trace.reasons), trace=trace)

        handoff = StartHandoffPlan(
            profile=plan.profile,
            chemistry=plan.chemistry,
            recipe_id=plan.recipe_id,
            target_voltage_v=plan.target_preview.voltage_v,
            target_current_a=plan.target_preview.current_a,
            mode=mode,
            controller_handoff="deferred_no_mutation",
            physical_execution=False,
        )
        reason = "shadow_trace_created" if mode is StartExecutionMode.SHADOW else "dry_run_handoff_created"
        return StartAdapterResult(True, mode, reason, trace=trace, handoff_plan=handoff)

    async def dry_run_integration(
        self,
        plan: ApprovedStartPlan,
        app: Any,
        *,
        handoff_probe: Callable[[ApprovedStartPlan], Any] | None = None,
    ) -> StartDryRunReport:
        """Inspect the real V2 composition through the DRY_RUN-only gate."""
        return await StartDryRunIntegrationGate().evaluate(
            plan,
            app,
            handoff_probe=handoff_probe,
        )

    def _active(self, plan: ApprovedStartPlan) -> StartAdapterResult:
        if not self.active_enabled:
            return StartAdapterResult(False, StartExecutionMode.ACTIVE, "active_execution_disabled")
        if self.active_handoff is None:
            return StartAdapterResult(False, StartExecutionMode.ACTIVE, "active_handoff_not_configured")
        raise RuntimeError("ACTIVE START handoff requires a separately approved production gate")
