from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from pb_domain import (
    BatteryChemistry,
    BatteryCondition,
    BatteryIdentity,
    ChargeContext,
    ChargeIntent,
)
from recipe_engine import RecipeEnvelope, select_recipe_envelope


PROFILE_CHEMISTRY = {
    "Ca/Ca": BatteryChemistry.CA_CA,
    "EFB": BatteryChemistry.EFB,
    "AGM": BatteryChemistry.AGM,
    "Custom": BatteryChemistry.CUSTOM,
}

HV_STAGE_NAMES = frozenset({"mix mode", "десульфатация", "desulfation", "conditioning", "recovery"})


@dataclass(frozen=True)
class LegacyRecipeAuthorization:
    envelope: RecipeEnvelope
    target_voltage_v: float
    target_current_a: float
    stage_kind: str
    allowed: bool
    reason: str


def chemistry_for_legacy_profile(profile: str) -> BatteryChemistry:
    try:
        return PROFILE_CHEMISTRY[str(profile)]
    except KeyError as exc:
        raise ValueError(f"unknown legacy profile: {profile!r}") from exc


def build_legacy_charge_context(
    *,
    profile: str,
    capacity_ah: float,
    battery_id: str,
    intent: ChargeIntent,
    condition: BatteryCondition = BatteryCondition.UNKNOWN,
    manufacturer: str = "",
    model: str = "",
) -> ChargeContext:
    identity = BatteryIdentity(
        battery_id=str(battery_id),
        chemistry=chemistry_for_legacy_profile(profile),
        nominal_capacity_ah=float(capacity_ah),
        manufacturer=str(manufacturer),
        model=str(model),
    )
    return ChargeContext(
        identity=identity,
        intent=intent,
        condition=condition,
    )


def authorize_legacy_target(
    context: ChargeContext,
    *,
    stage: str,
    target_voltage_v: float,
    target_current_a: float,
    expert_high_voltage: bool = False,
    custom_voltage_ceiling_v: Optional[float] = None,
    hardware_max_current_a: float = 12.0,
) -> LegacyRecipeAuthorization:
    envelope = select_recipe_envelope(
        context,
        expert_high_voltage=expert_high_voltage,
        custom_voltage_ceiling_v=custom_voltage_ceiling_v,
        hardware_max_current_a=hardware_max_current_a,
    )
    stage_key = " ".join(str(stage).strip().lower().replace("_", " ").split())
    stage_kind = "hv" if stage_key in HV_STAGE_NAMES else "main"
    current_ceiling = (
        envelope.hv_current_limit_a if stage_kind == "hv" else envelope.main_current_limit_a
    )

    voltage_ok = envelope.allows_voltage(target_voltage_v)
    current_ok = float(target_current_a) <= current_ceiling + 1e-9
    allowed = voltage_ok and current_ok
    reasons = []
    if not voltage_ok:
        reasons.append(
            f"target {float(target_voltage_v):.2f}V exceeds recipe ceiling "
            f"{envelope.voltage_ceiling_v:.2f}V"
        )
    if not current_ok:
        reasons.append(
            f"target {float(target_current_a):.2f}A exceeds {stage_kind} current ceiling "
            f"{current_ceiling:.2f}A"
        )
    if not reasons:
        reasons.append("target is inside recipe envelope")

    return LegacyRecipeAuthorization(
        envelope=envelope,
        target_voltage_v=float(target_voltage_v),
        target_current_a=float(target_current_a),
        stage_kind=stage_kind,
        allowed=allowed,
        reason="; ".join(reasons),
    )
