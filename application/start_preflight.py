"""Read-only START preflight; no controller/session/HA mutation is allowed."""

from __future__ import annotations

from typing import Any, Mapping

from legacy_recipe_adapter import chemistry_for_legacy_profile
from pb_domain import BatteryIdentity, ChargeContext
from recipe_engine import select_recipe_envelope
from runtime.ui.commands.models import CommandResult, CommandStatus, DomainIntent
from safe_output import OutputRequest, SafetySupervisor, snapshot_from_live

from .intents import OperatorIntent, OperatorIntentKind
from .start_request import (
    StartPreflightComparison,
    StartPreflightResult,
    StartRequest,
    TargetPreview,
)


INITIAL_MAIN_THRESHOLD_V = 12.0


class StartPreflightService:
    """Evaluate the existing V2 START contract without executing it."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def evaluate(self, request: StartRequest) -> StartPreflightResult:
        reasons: list[str] = []
        ownership = self._ownership_status()
        if ownership != "available":
            reasons.append(ownership)

        controller = getattr(self.app, "charge_controller", None)
        if controller is not None and bool(getattr(controller, "is_active", False)):
            reasons.append("active_charge_session")

        try:
            chemistry = chemistry_for_legacy_profile(request.profile)
        except ValueError as exc:
            return StartPreflightResult(
                False,
                tuple(reasons + ["invalid_profile", str(exc)]),
                ownership,
                "not_checked",
                "not_checked",
                profile=request.profile,
            )

        identity = request.battery_identity or BatteryIdentity(
            battery_id=request.battery_id,
            chemistry=chemistry,
            nominal_capacity_ah=float(request.capacity_ah),
        )
        if identity.chemistry is not chemistry:
            reasons.append("profile_chemistry_mismatch")
        if abs(float(identity.nominal_capacity_ah) - float(request.capacity_ah)) > 1e-9:
            reasons.append("profile_capacity_mismatch")

        live = await self.app.hass.get_all_live()
        snapshot = snapshot_from_live(live)
        if snapshot is None:
            return StartPreflightResult(
                False,
                tuple(reasons + ["invalid_or_stale_telemetry"]),
                ownership,
                "denied",
                "not_checked",
                profile=request.profile,
                chemistry=chemistry.value,
            )
        telemetry_status = "valid"
        if snapshot.output_on:
            reasons.append("output_already_on")

        try:
            context = ChargeContext(identity=identity, intent=request.intent, condition=request.condition)
            recipe = select_recipe_envelope(context, expert_high_voltage=False)
        except (KeyError, TypeError, ValueError) as exc:
            return StartPreflightResult(
                False,
                tuple(reasons + ["recipe_selection_failed", str(exc)]),
                ownership,
                telemetry_status,
                "not_checked",
                profile=request.profile,
                chemistry=chemistry.value,
            )

        target = self._target_preview(
            controller,
            snapshot.battery_voltage_v,
            snapshot.temp_ext_c,
            request.profile,
            request.capacity_ah,
            recipe,
        )
        if target is None:
            reasons.append("target_preview_unavailable")
            return StartPreflightResult(
                False,
                tuple(reasons),
                ownership,
                telemetry_status,
                "not_checked",
                recipe,
                profile=request.profile,
                chemistry=chemistry.value,
            )

        current = self._cap_current(target.current_a)
        safety_request = OutputRequest(
            voltage_v=target.voltage_v,
            current_a=current,
            ovp_v=target.voltage_v + float(getattr(self.app, "OVP_OFFSET", 0.1)),
            ocp_a=current + float(getattr(self.app, "OCP_OFFSET", 0.1)),
            recipe_voltage_ceiling_v=recipe.voltage_ceiling_v,
        )
        policy = getattr(getattr(self.app.hass, "_safety_supervisor", None), "policy", None)
        safety = SafetySupervisor(policy).preflight(safety_request, snapshot)
        if not safety.allowed:
            reasons.extend(sorted(item.value for item in safety.violations))
        safety_status = "allowed" if safety.allowed else "denied"
        return StartPreflightResult(
            not reasons and safety.allowed,
            tuple(dict.fromkeys(reasons)),
            ownership,
            telemetry_status,
            safety_status,
            recipe,
            TargetPreview(target.voltage_v, current, target.stage, target.prep_skipped),
            request.profile,
            chemistry.value,
            identity,
            {
                "battery_voltage_v": snapshot.battery_voltage_v,
                "temperature_ext_c": snapshot.temp_ext_c,
                "output_on": snapshot.output_on,
                "active_session": bool(getattr(controller, "is_active", False)),
            },
        )

    def _ownership_status(self) -> str:
        manager = getattr(self.app, "rd_control_mode_manager", None)
        if manager is not None and bool(getattr(manager, "hands_off", False)):
            return "hands_off"
        return "available"

    def _cap_current(self, value: float) -> float:
        cap = getattr(self.app, "_cap_current", None)
        return float(cap(value)) if callable(cap) else float(value)

    @staticmethod
    def _target_preview(
        controller: Any,
        battery_v: float,
        temp_ext: float,
        profile: str,
        capacity_ah: float,
        recipe: Any,
    ):
        if controller is None:
            return None
        method = getattr(controller, "_prep_target" if battery_v < INITIAL_MAIN_THRESHOLD_V else "_main_target", None)
        if not callable(method):
            return None
        voltage, _controller_current = method(temp_ext)
        is_main = battery_v >= INITIAL_MAIN_THRESHOLD_V
        if is_main:
            # The request is authoritative for preflight.  The controller may still
            # contain the previous session's capacity until the real START handoff.
            current = float(recipe.main_current_limit_a)
        else:
            # Keep the existing PREP rule (~0.01C), but derive it from this request,
            # not from stale controller state.
            current = min(12.0, max(0.1, float(capacity_ah) * 0.01))
        return TargetPreview(
            float(voltage),
            current,
            "MAIN" if is_main else "PREP",
            is_main,
        )


class StartCommandHandler:
    """Application routing adapter for START preflight only."""

    def __init__(self, service: StartPreflightService) -> None:
        self.service = service

    async def preflight(self, request: StartRequest) -> StartPreflightResult:
        return await self.service.evaluate(request)

    async def route(self, intent: OperatorIntent) -> CommandResult:
        if intent.kind is not OperatorIntentKind.START_CHARGE:
            return CommandResult(CommandStatus.REJECTED, "invalid_start_intent")
        return CommandResult(
            CommandStatus.ACCEPTED,
            "start_preflight_requires_explicit_request",
            DomainIntent(kind=OperatorIntentKind.START_CHARGE.value, payload=dict(intent.parameters)),
        )


def compare_start_preflight(
    v2: Mapping[str, Any],
    v3: StartPreflightResult,
) -> StartPreflightComparison:
    """Compare a captured/non-executing V2 preview with the V3 result."""
    v3_data = {
        "profile": v3.profile,
        "chemistry": v3.chemistry,
        "allowed": v3.allowed,
        "ownership_status": v3.ownership_status,
        "telemetry_status": v3.telemetry_status,
        "safety_status": v3.safety_status,
        "recipe_id": v3.recipe_preview.recipe_id if v3.recipe_preview else None,
        "target_voltage_v": v3.target_preview.voltage_v if v3.target_preview else None,
        "target_current_a": v3.target_preview.current_a if v3.target_preview else None,
    }
    fields = tuple(sorted(key for key in set(v2) | set(v3_data) if v2.get(key) != v3_data.get(key)))
    return StartPreflightComparison("MATCH" if not fields else "MISMATCH", fields, dict(v2), v3_data)
