"""Pure V3 charge-program boundary.

This package is intentionally not imported by the production V2 composition.
It resolves a complete immutable program for shadow/domain use only.
"""

from .models import (
    BatteryProfile,
    ChargeProgram,
    Chemistry,
    Condition,
    CurrentPolicy,
    ManualProgramInput,
    Mode,
    OwnedValue,
    ParameterOwner,
    Phase,
    SafetyReference,
    Timer,
    TransitionRule,
    VoltagePolicy,
)
from .resolver import ChargeProgramResolver, resolve_charge_program
from .program_ids import ProgramIdResolver
from .identity import ProgramIdentity, ProgramIdentityRegistry
from .catalog import ProgramDefaults, SafetyDefaults
from .manual_presets import requested_manual_program_input

__all__ = [
    "BatteryProfile",
    "ChargeProgram",
    "Chemistry",
    "Condition",
    "CurrentPolicy",
    "ManualProgramInput",
    "Mode",
    "OwnedValue",
    "ParameterOwner",
    "Phase",
    "SafetyReference",
    "Timer",
    "TransitionRule",
    "VoltagePolicy",
    "ChargeProgramResolver",
    "resolve_charge_program",
    "ProgramIdResolver",
    "ProgramIdentity",
    "ProgramIdentityRegistry",
    "ProgramDefaults",
    "SafetyDefaults",
    "requested_manual_program_input",
]
