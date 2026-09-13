"""Pure charge data and program contracts for the staged V3 migration."""

from .battery import BatteryProfile
from .chemistry import ChemistryProfile, ProductionChemistry, map_production_chemistry
from .engine import ChargeEngine
from .intent import ChargeIntent
from .limits import ChargeLimits
from .measurements import Measurements
from .post import FinishIntent
from .profiles import RecipeDTO, ValidatedChargeRecipe, RecipeRegistry, ChargeRecipeValidator
from .program import ChargeProgram
from .state import ChargeState, DeltaRuntimeState
from .adapters import LegacyChargeProgramAdapter
from .shadow import ChargeDecisionShadow, ComparisonResult, DecisionComparison
from .programs import ManualProgram, ManualTargets
from .programs import MinimumConfig, MinimumProgram
from .programs import DeltaConfig, DeltaProgram
from .registry import ProgramRegistry
from .strategy import (
    ChargeRecipe, ChargeStrategy, StrategyRuntimeState,
    MainPolicy, MainPolicyConfig, RecoveryPolicy, RecoveryPolicyConfig,
    MixPolicy, MixPolicyConfig, CCMixExitPolicy, CCMixExitConfig,
    CVMixExitPolicy, CVMixExitConfig, MixAuthorityState,
)
from .service import ChargeRuntimeSnapshot, ChargeService
from .contracts import (
    ChargeDecisionCase,
    DecisionMismatch,
    DecisionValidationResult,
    DecisionValidationStatus,
    validate_case,
)
from .contracts import DELTA_TRANSITIONS, DeltaDecisionCase, DeltaState, delta_cases

__all__ = [
    "BatteryProfile",
    "ChargeEngine",
    "ChargeIntent",
    "ChargeLimits",
    "ChargeProgram",
    "ChargeState",
    "ChemistryProfile",
    "ProductionChemistry",
    "map_production_chemistry",
    "DeltaRuntimeState",
    "LegacyChargeProgramAdapter",
    "Measurements",
    "FinishIntent",
    "RecipeDTO", "ValidatedChargeRecipe", "RecipeRegistry", "ChargeRecipeValidator",
    "ChargeDecisionShadow",
    "ComparisonResult",
    "DecisionComparison",
    "ManualProgram",
    "ManualTargets",
    "MinimumConfig",
    "MinimumProgram",
    "DeltaConfig",
    "DeltaProgram",
    "ProgramRegistry",
    "ChargeRuntimeSnapshot",
    "ChargeService",
    "ChargeDecisionCase",
    "DELTA_TRANSITIONS",
    "DeltaDecisionCase",
    "DeltaState",
    "DecisionMismatch",
    "DecisionValidationResult",
    "DecisionValidationStatus",
    "delta_cases",
    "validate_case",
    "ChargeRecipe", "ChargeStrategy", "StrategyRuntimeState",
    "MainPolicy", "MainPolicyConfig", "RecoveryPolicy", "RecoveryPolicyConfig",
    "MixPolicy", "MixPolicyConfig", "CCMixExitPolicy", "CCMixExitConfig",
    "CVMixExitPolicy", "CVMixExitConfig", "MixAuthorityState",
]
