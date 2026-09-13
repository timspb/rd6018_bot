"""Pure charge data and program contracts for the staged V3 migration."""

from .battery import BatteryProfile
from .chemistry import ChemistryProfile
from .engine import ChargeEngine
from .intent import ChargeIntent
from .limits import ChargeLimits
from .measurements import Measurements
from .program import ChargeProgram
from .state import ChargeState
from .adapters import LegacyChargeProgramAdapter
from .shadow import ChargeDecisionShadow, ComparisonResult, DecisionComparison
from .programs import ManualProgram, ManualTargets
from .programs import MinimumConfig, MinimumProgram

__all__ = [
    "BatteryProfile",
    "ChargeEngine",
    "ChargeIntent",
    "ChargeLimits",
    "ChargeProgram",
    "ChargeState",
    "ChemistryProfile",
    "LegacyChargeProgramAdapter",
    "Measurements",
    "ChargeDecisionShadow",
    "ComparisonResult",
    "DecisionComparison",
    "ManualProgram",
    "ManualTargets",
    "MinimumConfig",
    "MinimumProgram",
]
