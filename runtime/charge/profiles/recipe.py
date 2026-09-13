"""Factory and validated recipe data; no actuator or transport dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..battery import BatteryProfile
from ..chemistry import ChemistryProfile, ProductionChemistry, map_production_chemistry
from ..strategy import (
    CCMixExitConfig, CVMixExitConfig, ChargeRecipe, MainFallbackPolicy,
    MainFallbackPolicyConfig, MainPolicy, MainPolicyConfig, MixPolicy,
    MixPolicyConfig, PlateauDetector, PlateauDetectorConfig, RecoveryPolicy,
    RecoveryPolicyConfig,
)


@dataclass(frozen=True)
class RecipeDTO:
    """Serialization-ready input contract for a future profile editor."""

    chemistry: str
    overrides: Mapping[str, Any]
    base_chemistry: str | None = None


@dataclass(frozen=True)
class ValidatedChargeRecipe:
    chemistry: ChemistryProfile
    recipe: ChargeRecipe
    source: str

    def to_battery_profile(self, capacity_ah: float, *, manufacturer: str | None = None) -> BatteryProfile:
        return BatteryProfile(self.chemistry, capacity_ah, manufacturer=manufacturer, recipe=self.recipe)


def factory_recipe(chemistry: ProductionChemistry | ChemistryProfile | str) -> ValidatedChargeRecipe:
    label = getattr(chemistry, "value", chemistry)
    if str(label).strip().upper() == "CUSTOM":
        raise ValueError("CUSTOM requires an explicit recipe definition")
    profile = chemistry if isinstance(chemistry, ChemistryProfile) else map_production_chemistry(chemistry)
    # Factory values are data here, not algorithm constants.  They are kept
    # explicit per chemistry so a future editor can validate/override them.
    if profile == ChemistryProfile.AGM:
        main = MainPolicyConfig(15.0, 8.0, 0.2, 7200.0, 0.2, 7200.0)
        recovery = RecoveryPolicyConfig(4, 16.3, 1.6, recovery_seconds=7200.0, exhausted_action="remain_main")
        fallback = MainFallbackPolicy(MainFallbackPolicyConfig(259200.0, "AGM", 0.2, main_voltage=15.0, main_current=8.0))
        detector = PlateauDetector(PlateauDetectorConfig(3, 0.05, 0.2, 0.02))
        cc = CCMixExitConfig(16.3, 0.03, 3, 7200.0, 16.3, 2.4)
        cv = CVMixExitConfig(0.2, 0.06, 3, 7200.0, 16.3, 2.4, containment_start_seconds=1800.0, containment_recalc_seconds=600.0, containment_headroom_a=0.4)
        authority = 36000.0
    elif profile == ChemistryProfile.EFB:
        main = MainPolicyConfig(14.8, 7.0, 0.3, 10800.0, 0.3, 2400.0)
        recovery = RecoveryPolicyConfig(3, 16.3, 1.4, recovery_seconds=7200.0)
        fallback = MainFallbackPolicy(MainFallbackPolicyConfig(259200.0, "EFB", 0.3, main_voltage=14.8, main_current=7.0))
        detector = PlateauDetector(PlateauDetectorConfig(3, 0.05, 0.3, 0.02))
        cc = CCMixExitConfig(16.5, 0.03, 3, 7200.0, 16.5, 2.1)
        cv = CVMixExitConfig(0.3, 0.09, 3, 7200.0, 16.5, 2.1, containment_start_seconds=1800.0, containment_recalc_seconds=600.0, containment_headroom_a=0.4)
        authority = 86400.0
    else:
        main = MainPolicyConfig(14.7, 7.0, 0.3, 10800.0, 0.3, 2400.0)
        recovery = RecoveryPolicyConfig(3, 16.3, 1.4, recovery_seconds=7200.0)
        fallback = MainFallbackPolicy(MainFallbackPolicyConfig(259200.0, "CALCIUM", 0.3, main_voltage=14.7, main_current=7.0))
        detector = PlateauDetector(PlateauDetectorConfig(3, 0.05, 0.3, 0.02))
        cc = CCMixExitConfig(16.5, 0.03, 3, 7200.0, 16.5, 2.1)
        cv = CVMixExitConfig(0.3, 0.09, 3, 7200.0, 16.5, 2.1, containment_start_seconds=1800.0, containment_recalc_seconds=600.0, containment_headroom_a=0.4)
        authority = 72000.0
    strategy_main = MainPolicy(main, plateau_detector=detector)
    recipe = ChargeRecipe(
        strategy_main,
        RecoveryPolicy(recovery),
        MixPolicy(MixPolicyConfig(authority, cc, cv)),
        fallback=fallback,
    )
    return ValidatedChargeRecipe(profile, recipe, "factory")
