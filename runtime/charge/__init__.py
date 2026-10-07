"""Pure charge data and program contracts for the staged V3 migration.

Leaf-module imports are lazy so a strategy import does not compose unrelated
profiles, adapters, or the historical controller graph.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "BatteryProfile": (".battery", "BatteryProfile"),
    "ChemistryProfile": (".chemistry", "ChemistryProfile"),
    "ProductionChemistry": (".chemistry", "ProductionChemistry"),
    "map_production_chemistry": (".chemistry", "map_production_chemistry"),
    "ChargeEngine": (".engine", "ChargeEngine"),
    "ActuatorIntent": (".decisions", "ActuatorIntent"),
    "ContainmentResultRequest": (".decisions", "ContainmentResultRequest"),
    "DomainDecision": (".decisions", "DomainDecision"),
    "ProfileDefinition": (".profile_registry", "ProfileDefinition"),
    "ProfileRegistry": (".profile_registry", "ProfileRegistry"),
    "StrategyEngine": (".strategy_engine", "StrategyEngine"),
    "SessionManager": (".session", "SessionManager"),
    "SessionSnapshot": (".session", "SessionSnapshot"),
    "SessionStatus": (".session", "SessionStatus"),
    "ChargeIntent": (".intent", "ChargeIntent"),
    "ChargeLimits": (".limits", "ChargeLimits"),
    "Measurements": (".measurements", "Measurements"),
    "FinishIntent": (".post", "FinishIntent"),
    "RecipeDTO": (".profiles", "RecipeDTO"),
    "ValidatedChargeRecipe": (".profiles", "ValidatedChargeRecipe"),
    "RecipeRegistry": (".profiles", "RecipeRegistry"),
    "ChargeRecipeValidator": (".profiles", "ChargeRecipeValidator"),
    "ChargeProgram": (".program", "ChargeProgram"),
    "ChargeState": (".state", "ChargeState"),
    "DeltaRuntimeState": (".state", "DeltaRuntimeState"),
    "ManualProgram": (".programs", "ManualProgram"),
    "ManualTargets": (".programs", "ManualTargets"),
    "MinimumConfig": (".programs", "MinimumConfig"),
    "MinimumProgram": (".programs", "MinimumProgram"),
    "DeltaConfig": (".programs", "DeltaConfig"),
    "DeltaProgram": (".programs", "DeltaProgram"),
    "ProgramRegistry": (".registry", "ProgramRegistry"),
    "ChargeRecipe": (".strategy", "ChargeRecipe"),
    "ChargeStrategy": (".strategy", "ChargeStrategy"),
    "StrategyRuntimeState": (".strategy", "StrategyRuntimeState"),
    "MainPolicy": (".strategy", "MainPolicy"),
    "MainPolicyConfig": (".strategy", "MainPolicyConfig"),
    "RecoveryPolicy": (".strategy", "RecoveryPolicy"),
    "RecoveryPolicyConfig": (".strategy", "RecoveryPolicyConfig"),
    "MixPolicy": (".strategy", "MixPolicy"),
    "MixPolicyConfig": (".strategy", "MixPolicyConfig"),
    "CCMixExitPolicy": (".strategy", "CCMixExitPolicy"),
    "CCMixExitConfig": (".strategy", "CCMixExitConfig"),
    "CVMixExitPolicy": (".strategy", "CVMixExitPolicy"),
    "CVMixExitConfig": (".strategy", "CVMixExitConfig"),
    "MixAuthorityState": (".strategy", "MixAuthorityState"),
    "MixCurrentContainmentState": (".strategy", "MixCurrentContainmentState"),
    "ResetProtectionIntent": (".strategy", "ResetProtectionIntent"),
    "post_mix_reset_intent": (".strategy", "post_mix_reset_intent"),
    "emergency_stop_reset_intent": (".strategy", "emergency_stop_reset_intent"),
    "MixTemperatureDecision": (".strategy", "MixTemperatureDecision"),
    "MixTemperatureIntegrityPolicy": (".strategy", "MixTemperatureIntegrityPolicy"),
    "ChargeRuntimeSnapshot": (".service", "ChargeRuntimeSnapshot"),
    "ChargeService": (".service", "ChargeService"),
    "ChargeDecisionCase": (".contracts", "ChargeDecisionCase"),
    "DecisionMismatch": (".contracts", "DecisionMismatch"),
    "DecisionValidationResult": (".contracts", "DecisionValidationResult"),
    "DecisionValidationStatus": (".contracts", "DecisionValidationStatus"),
    "validate_case": (".contracts", "validate_case"),
    "DELTA_TRANSITIONS": (".contracts", "DELTA_TRANSITIONS"),
    "DeltaDecisionCase": (".contracts", "DeltaDecisionCase"),
    "DeltaState": (".contracts", "DeltaState"),
    "delta_cases": (".contracts", "delta_cases"),
}

__all__ = list(_EXPORTS)

def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, symbol = target
    value = getattr(import_module(module_name, __name__), symbol)
    globals()[name] = value
    return value
