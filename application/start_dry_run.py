"""Read-only integration gate for the future V3 START handoff."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from safe_output import snapshot_from_live

from .start_plan import ApprovedStartPlan


@dataclass(frozen=True)
class StartDryRunReport:
    plan: ApprovedStartPlan
    allowed: bool
    ownership_decision: str
    session_decision: str
    controller_handoff_decision: str
    rollback_plan: tuple[str, ...]
    transaction_order: tuple[str, ...]
    physical_execution_blocked_reason: str
    reasons: tuple[str, ...] = ()


class StartDryRunIntegrationGate:
    """Inspect real V2 composition objects without invoking their mutators."""

    TRANSACTION_ORDER = (
        "validate_profile_and_recipe",
        "validate_ownership",
        "validate_session_idle",
        "read_telemetry",
        "handoff_controller_deferred",
        "physical_execution_blocked",
    )
    ROLLBACK_PLAN = (
        "no_session_mutation_in_dry_run",
        "preserve_confirmed_output_off",
        "future_failure_requires_verified_off",
    )

    async def evaluate(
        self,
        plan: ApprovedStartPlan,
        app: Any,
        *,
        handoff_probe: Callable[[ApprovedStartPlan], bool | Awaitable[bool]] | None = None,
    ) -> StartDryRunReport:
        reasons: list[str] = []

        manager = getattr(app, "rd_control_mode_manager", None)
        ownership = "available" if not bool(getattr(manager, "hands_off", False)) else "hands_off"
        if ownership != "available" or plan.ownership_result != "available":
            reasons.append("ownership_not_available")

        controller = getattr(app, "charge_controller", None)
        active = bool(getattr(controller, "is_active", False))
        session = "active" if active else "clear"
        if active:
            reasons.append("active_charge_session")

        telemetry = None
        hass = getattr(app, "hass", None)
        get_all_live = getattr(hass, "get_all_live", None)
        if not callable(get_all_live):
            reasons.append("live_read_not_available")
        else:
            live = await get_all_live()
            telemetry = snapshot_from_live(live)
            if telemetry is None:
                reasons.append("invalid_or_stale_telemetry")
            elif telemetry.output_on:
                reasons.append("output_already_on")

        handoff = "deferred_read_only"
        if controller is None:
            reasons.append("controller_not_available")
        elif handoff_probe is not None:
            probe_result = handoff_probe(plan)
            if hasattr(probe_result, "__await__"):
                probe_result = await probe_result
            if not probe_result:
                handoff = "probe_denied"
                reasons.append("controller_handoff_probe_failed")

        return StartDryRunReport(
            plan=plan,
            allowed=not reasons,
            ownership_decision=ownership,
            session_decision=session,
            controller_handoff_decision=handoff,
            rollback_plan=self.ROLLBACK_PLAN,
            transaction_order=self.TRANSACTION_ORDER,
            physical_execution_blocked_reason="dry_run_physical_execution_disabled",
            reasons=tuple(dict.fromkeys(reasons)),
        )
