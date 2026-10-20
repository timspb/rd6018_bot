"""Recipe-envelope target bounds for the single production session host."""

from __future__ import annotations

from typing import Any, Optional, Tuple

from application.recipe_policy import chemistry_for_profile
from pb_domain import BatteryCondition, BatteryIdentity, ChargeContext, ChargeIntent
from recipe_engine import RecipeEnvelope, select_recipe_envelope


def recipe_envelope(
    *, profile: str, capacity_ah: int, battery_id: Optional[str],
    intent: ChargeIntent, condition: BatteryCondition,
) -> Optional[RecipeEnvelope]:
    """Resolve the existing automatic envelope; Custom retains its existing bypass."""
    if profile == "Custom":
        return None
    chemistry = chemistry_for_profile(profile)
    identity = BatteryIdentity(
        battery_id=battery_id or f"runtime:{profile}",
        chemistry=chemistry,
        nominal_capacity_ah=float(max(1, capacity_ah)),
    )
    return select_recipe_envelope(
        ChargeContext(identity=identity, intent=intent, condition=condition),
        expert_high_voltage=False,
    )


def bound_target(
    target: Tuple[float, float], envelope: Optional[RecipeEnvelope], *, hv: bool,
) -> Tuple[float, float]:
    """Apply the canonical recipe voltage and stage-specific current ceilings."""
    if envelope is None:
        return target
    voltage_v, current_a = float(target[0]), float(target[1])
    current_limit = envelope.hv_current_limit_a if hv else envelope.main_current_limit_a
    return min(voltage_v, float(envelope.voltage_ceiling_v)), min(current_a, float(current_limit))


def is_production_host(host: Any) -> bool:
    """Identify the production extension fields on the one canonical host."""
    return hasattr(host, "_v2_cooling_pause")


def bound_host_target(host: Any, target: Tuple[float, float], *, hv: bool) -> Tuple[float, float]:
    """Apply production recipe bounds using context already held by the host."""
    if not is_production_host(host):
        return target
    envelope = recipe_envelope(
        profile=host.battery_type,
        capacity_ah=host.ah_capacity,
        battery_id=host._v2_battery_id,
        intent=host._v2_intent,
        condition=host._v2_condition_before,
    )
    return bound_target(target, envelope, hv=hv)


__all__ = ["bound_host_target", "bound_target", "is_production_host", "recipe_envelope"]
