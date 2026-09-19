"""Immutable, infrastructure-free V3 charge-program contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Tuple



class Mode(str, Enum):
    AUTO = "AUTO"
    MANUAL = "MANUAL"


class Chemistry(str, Enum):
    CALCIUM = "CALCIUM"
    EFB = "EFB"
    AGM = "AGM"

    @classmethod
    def parse(cls, value: str | "Chemistry") -> "Chemistry":
        if isinstance(value, cls):
            return value
        try:
            from .identity import ProgramIdentityRegistry
            return ProgramIdentityRegistry().chemistry(str(value))
        except ValueError as exc:
            raise ValueError(f"unsupported V3 chemistry identity: {value!r}") from exc


class ParameterOwner(str, Enum):
    BATTERY_PROFILE = "battery_profile"
    MANUAL_PROGRAM = "manual_program"
    SAFETY_POLICY = "safety_policy"


@dataclass(frozen=True)
class OwnedValue:
    """A value with explicit authority; no implicit/global parameter owner."""

    name: str
    value: Any
    owner: ParameterOwner

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ValueError("owned parameter name is required")
        if self.value is None:
            raise ValueError(f"owned parameter {self.name!r} cannot be None")


@dataclass(frozen=True)
class BatteryProfile:
    battery_id: str
    chemistry: Chemistry | str
    capacity_ah: float
    manufacturer: str = ""
    model: str = ""

    def __post_init__(self) -> None:
        if not str(self.battery_id).strip():
            raise ValueError("battery_id is required")
        if float(self.capacity_ah) <= 0:
            raise ValueError("capacity_ah must be positive")
        object.__setattr__(self, "chemistry", Chemistry.parse(self.chemistry))


@dataclass(frozen=True)
class VoltagePolicy:
    target: OwnedValue
    ceiling: OwnedValue


@dataclass(frozen=True)
class CurrentPolicy:
    target: OwnedValue
    ceiling: OwnedValue


@dataclass(frozen=True)
class Timer:
    name: str
    seconds: float
    owner: ParameterOwner

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ValueError("timer name is required")
        if float(self.seconds) < 0:
            raise ValueError("timer cannot be negative")


@dataclass(frozen=True)
class Condition:
    name: str
    expression: str
    owner: ParameterOwner

    def __post_init__(self) -> None:
        if not str(self.name).strip() or not str(self.expression).strip():
            raise ValueError("condition name and expression are required")


@dataclass(frozen=True)
class SafetyReference:
    name: str
    value: Any
    owner: ParameterOwner = ParameterOwner.SAFETY_POLICY

    def __post_init__(self) -> None:
        if self.owner is not ParameterOwner.SAFETY_POLICY:
            raise ValueError("safety references must be owned by safety_policy")


@dataclass(frozen=True)
class Phase:
    phase_id: str
    voltage: VoltagePolicy
    current: CurrentPolicy
    timers: Tuple[Timer, ...] = ()
    conditions: Tuple[Condition, ...] = ()
    emits_setpoints: bool = True

    def __post_init__(self) -> None:
        if not str(self.phase_id).strip():
            raise ValueError("phase_id is required")


@dataclass(frozen=True)
class TransitionRule:
    """Program-owned transition; the engine only evaluates its generic shape."""

    source_phase: str
    target_phase: str
    condition_key: str

    def __post_init__(self) -> None:
        if not str(self.source_phase).strip() or not str(self.target_phase).strip():
            raise ValueError("transition phases are required")
        if not str(self.condition_key).strip():
            raise ValueError("transition condition_key is required")


@dataclass(frozen=True)
class ManualProgramInput:
    """Explicit operator values; it contains no runtime/controller reference."""

    main_voltage_v: float
    main_current_a: float
    mix_voltage_v: float
    mix_current_a: float
    delta_voltage_v: float
    delta_current_a: float
    hold_hours: float
    max_mix_hours: float = 24.0
    main_imin_a: float | None = None
    main_hold_hours: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "main_voltage_v",
            "main_current_a",
            "mix_voltage_v",
            "mix_current_a",
            "delta_voltage_v",
            "delta_current_a",
        ):
            if float(getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be positive")
        if float(self.hold_hours) < 0 or float(self.max_mix_hours) <= 0:
            raise ValueError("manual hold/max_mix_hours values are invalid")
        if self.main_imin_a is not None and not 0 < float(self.main_imin_a) <= float(self.main_current_a):
            raise ValueError("manual MAIN Imin must be positive and not exceed main current")
        if float(self.main_hold_hours) < 0:
            raise ValueError("manual MAIN hold must not be negative")


@dataclass(frozen=True)
class ChargeProgram:
    """Complete deterministic program consumed by a future V3 FSM."""

    program_id: str
    mode: Mode
    battery_profile: BatteryProfile
    chemistry: Chemistry
    phases: Tuple[Phase, ...]
    voltage_policy: VoltagePolicy
    current_policy: CurrentPolicy
    timers: Tuple[Timer, ...]
    conditions: Tuple[Condition, ...]
    safety_references: Tuple[SafetyReference, ...]
    transitions: Tuple[TransitionRule, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.program_id).strip():
            raise ValueError("program_id is required")
        if not self.phases:
            raise ValueError("charge program must contain phases")
        if self.chemistry is not self.battery_profile.chemistry:
            raise ValueError("program chemistry must match battery profile")
        if not self.safety_references:
            raise ValueError("charge program must reference safety policy")
