from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from pb_domain import BatteryChemistry, BatteryCondition, ChargeContext, ChargeIntent


@dataclass(frozen=True)
class ChemistryPolicy:
    normal_voltage_ceiling_v: float
    recovery_voltage_ceiling_v: float
    expert_voltage_ceiling_v: float
    main_current_c_max: float
    hv_current_c_max: float


@dataclass(frozen=True)
class RecipeEnvelope:
    recipe_id: str
    chemistry: BatteryChemistry
    intent: ChargeIntent
    condition: BatteryCondition
    voltage_ceiling_v: float
    main_current_limit_a: float
    hv_current_limit_a: float
    expert_authorized: bool
    rationale: str

    def allows_voltage(self, target_v: float) -> bool:
        return float(target_v) <= self.voltage_ceiling_v + 1e-9


POLICIES: Dict[BatteryChemistry, ChemistryPolicy] = {
    BatteryChemistry.AGM: ChemistryPolicy(15.0, 16.3, 16.3, 0.10, 0.03),
    BatteryChemistry.EFB: ChemistryPolicy(14.8, 16.5, 17.5, 0.10, 0.05),
    BatteryChemistry.CA_CA: ChemistryPolicy(14.7, 16.5, 16.5, 0.10, 0.03),
    BatteryChemistry.FLOODED: ChemistryPolicy(14.8, 16.5, 16.5, 0.10, 0.05),
    BatteryChemistry.CUSTOM: ChemistryPolicy(16.6, 16.6, 18.0, 0.20, 0.20),
}


def _clamp_current(capacity_ah: float, c_rate: float, hardware_max_a: float) -> float:
    return min(float(hardware_max_a), max(0.0, float(capacity_ah) * float(c_rate)))


def select_recipe_envelope(
    context: ChargeContext,
    *,
    expert_high_voltage: bool = False,
    custom_voltage_ceiling_v: Optional[float] = None,
    hardware_max_current_a: float = 12.0,
) -> RecipeEnvelope:
    """Select policy limits; this does not choose stage setpoints.

    Existing ChargeController targets remain the recipe implementation during
    migration. This envelope answers the narrower authorization question:
    which target space is allowed for chemistry + intent + condition?
    """
    policy = POLICIES[context.identity.chemistry]
    chemistry = context.identity.chemistry
    intent = context.intent

    if chemistry == BatteryChemistry.CUSTOM and custom_voltage_ceiling_v is not None:
        requested = float(custom_voltage_ceiling_v)
        hard = (
            policy.expert_voltage_ceiling_v
            if expert_high_voltage
            else policy.normal_voltage_ceiling_v
        )
        ceiling = min(requested, hard)
        rationale = (
            f"Custom operator ceiling {requested:.2f}V, bounded by "
            f"{hard:.2f}V policy envelope."
        )
    elif intent in {ChargeIntent.NORMAL, ChargeIntent.DIAGNOSTIC}:
        ceiling = policy.normal_voltage_ceiling_v
        rationale = "Normal/diagnostic envelope; no recovery high-voltage authorization."
    elif intent == ChargeIntent.RECOVERY:
        ceiling = policy.recovery_voltage_ceiling_v
        rationale = "Recovery envelope explicitly selected by operator/workflow."
    elif intent == ChargeIntent.CONDITIONING:
        if expert_high_voltage:
            ceiling = policy.expert_voltage_ceiling_v
            rationale = "Expert conditioning envelope explicitly authorized."
        else:
            ceiling = policy.recovery_voltage_ceiling_v
            rationale = "Conditioning without expert high-voltage authorization."
    else:
        ceiling = policy.normal_voltage_ceiling_v
        rationale = "Conservative fallback envelope."

    if context.condition == BatteryCondition.REHYDRATED:
        rationale += " Battery is marked rehydrated; longitudinal cycle evidence is required."
    elif context.condition == BatteryCondition.DRY_SUSPECTED:
        rationale += " Dryness is suspected; high-voltage behavior must be interpreted with wetting state."

    return RecipeEnvelope(
        recipe_id=f"{chemistry.value}:{intent.value}",
        chemistry=chemistry,
        intent=intent,
        condition=context.condition,
        voltage_ceiling_v=ceiling,
        main_current_limit_a=_clamp_current(
            context.identity.nominal_capacity_ah,
            policy.main_current_c_max,
            hardware_max_current_a,
        ),
        hv_current_limit_a=_clamp_current(
            context.identity.nominal_capacity_ah,
            policy.hv_current_c_max,
            hardware_max_current_a,
        ),
        expert_authorized=bool(expert_high_voltage),
        rationale=rationale,
    )
