from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from legacy_recipe_adapter import LegacyRecipeAuthorization
from safe_output import EnableResult


class RecipeOutputAdapter(Protocol):
    async def safe_enable_output(
        self,
        *,
        voltage_v: float,
        current_a: float,
        ovp_v: float,
        ocp_a: float,
        recipe_voltage_ceiling_v: float,
        readback_delay_s: float = 0.0,
    ) -> EnableResult: ...


@dataclass(frozen=True)
class RecipeEnableResult:
    enabled: bool
    reason: str
    hardware_result: Optional[EnableResult] = None


async def enable_authorized_recipe_target(
    adapter: RecipeOutputAdapter,
    authorization: LegacyRecipeAuthorization,
    *,
    ovp_margin_v: float = 0.10,
    ocp_margin_a: float = 0.10,
    readback_delay_s: float = 0.0,
) -> RecipeEnableResult:
    """Enable one already-authorized recipe target through the fail-closed HW path.

    Authorization is evaluated before any hardware call. This prevents callers from
    using `safe_enable_output()` as a generic way around chemistry/intent policy.
    """
    if not authorization.allowed:
        return RecipeEnableResult(
            enabled=False,
            reason=f"recipe authorization denied: {authorization.reason}",
        )

    voltage_v = float(authorization.target_voltage_v)
    current_a = float(authorization.target_current_a)
    ovp_v = voltage_v + float(ovp_margin_v)
    ocp_a = current_a + float(ocp_margin_a)
    hardware = await adapter.safe_enable_output(
        voltage_v=voltage_v,
        current_a=current_a,
        ovp_v=ovp_v,
        ocp_a=ocp_a,
        recipe_voltage_ceiling_v=float(authorization.envelope.voltage_ceiling_v),
        readback_delay_s=float(readback_delay_s),
    )
    if not hardware.enabled:
        return RecipeEnableResult(
            enabled=False,
            reason=f"hardware safety gate denied enable: {hardware.detail}",
            hardware_result=hardware,
        )

    return RecipeEnableResult(
        enabled=True,
        reason=(
            f"enabled {authorization.envelope.recipe_id} {authorization.stage_kind} target "
            f"{voltage_v:.2f}V/{current_a:.2f}A"
        ),
        hardware_result=hardware,
    )
