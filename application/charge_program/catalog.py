"""V3 program catalog owned by the program/configuration boundary."""

from __future__ import annotations

from dataclasses import dataclass

from .models import (
    BatteryProfile, ChargeProgram, Chemistry, Condition, CurrentPolicy,
    ManualProgramInput, Mode, OwnedValue, ParameterOwner, Phase,
    SafetyReference, Timer, TransitionRule, VoltagePolicy,
)


@dataclass(frozen=True)
class ProgramDefaults:
    main_voltage_v: float
    main_current_a: float
    mix_voltage_v: float
    mix_authority_hours: float


AUTO_PROGRAM_DEFAULTS = {
    Chemistry.CALCIUM: ProgramDefaults(14.7, 7.0, 16.5, 20.0),
    Chemistry.EFB: ProgramDefaults(14.8, 7.0, 16.5, 24.0),
    Chemistry.AGM: ProgramDefaults(15.0, 8.0, 16.3, 10.0),
}


@dataclass(frozen=True)
class SafetyDefaults:
    auto_voltage_ceiling_v: float = 16.5
    manual_voltage_ceiling_v: float = 17.5
    current_ceiling_a: float = 12.0
    temperature_limit_c: float = 45.0
    telemetry_freshness_seconds: float = 300.0


def auto_defaults(battery: BatteryProfile) -> ProgramDefaults:
    return AUTO_PROGRAM_DEFAULTS[battery.chemistry]


def _owned(name: str, value: object, owner: ParameterOwner) -> OwnedValue:
    return OwnedValue(name=name, value=value, owner=owner)


def build_auto_program(battery: BatteryProfile, safety: SafetyDefaults) -> ChargeProgram:
    defaults = auto_defaults(battery)
    battery_owner = ParameterOwner.BATTERY_PROFILE
    safety_owner = ParameterOwner.SAFETY_POLICY
    main = Phase("main", VoltagePolicy(_owned("main_voltage_v", defaults.main_voltage_v, battery_owner), _owned("auto_voltage_ceiling_v", safety.auto_voltage_ceiling_v, safety_owner)), CurrentPolicy(_owned("main_current_a", defaults.main_current_a, battery_owner), _owned("current_ceiling_a", safety.current_ceiling_a, safety_owner)), timers=(Timer("main_tail_hold", 3 * 3600.0, battery_owner),), conditions=(Condition("main_to_mix", "confirmed end-of-main evidence", battery_owner),))
    mix_i = min(float(safety.current_ceiling_a), float(battery.capacity_ah) * 0.03)
    mix = Phase("mix", VoltagePolicy(_owned("mix_voltage_v", defaults.mix_voltage_v, battery_owner), _owned("auto_voltage_ceiling_v", safety.auto_voltage_ceiling_v, safety_owner)), CurrentPolicy(_owned("mix_current_a", mix_i, battery_owner), _owned("current_ceiling_a", safety.current_ceiling_a, safety_owner)), timers=(Timer("mix_authority", defaults.mix_authority_hours * 3600.0, battery_owner), Timer("mix_finish_hold", 2 * 3600.0, battery_owner)), conditions=(Condition("mix_delta", "CC confirmed delta-V or CV confirmed delta-I", battery_owner), Condition("mix_hold_complete", "confirmed finish hold elapsed", battery_owner)))
    transitions = (TransitionRule("prep", "main", "__entry__"), TransitionRule("main", "desulfation", "desulfation_requested"), TransitionRule("main", "mix", "main_complete"), TransitionRule("desulfation", "mix", "desulfation_complete"), TransitionRule("mix", "hold", "delta_confirmed"), TransitionRule("hold", "safe_wait", "hold_complete"), TransitionRule("safe_wait", "done", "safe_wait_complete"))
    refs = (SafetyReference("temperature_limit_c", safety.temperature_limit_c), SafetyReference("telemetry_freshness_seconds", safety.telemetry_freshness_seconds))
    return ChargeProgram(f"auto:{battery.chemistry.value.lower()}:{battery.battery_id}", Mode.AUTO, battery, battery.chemistry, (main, mix), main.voltage, main.current, main.timers + mix.timers, main.conditions + mix.conditions, refs, transitions)


def build_manual_program(battery: BatteryProfile, manual: ManualProgramInput, safety: SafetyDefaults) -> ChargeProgram:
    owner = ParameterOwner.MANUAL_PROGRAM
    safety_owner = ParameterOwner.SAFETY_POLICY
    main_conditions = [Condition("main_to_mix", "operator/profile hold complete", owner)]
    main_timers = []
    if manual.main_imin_a is not None:
        main_conditions.insert(0, Condition("main_imin", f"confirmed Imin >= {manual.main_imin_a:g} A", owner))
    if manual.main_hold_hours > 0:
        main_timers.append(Timer("main_hold", manual.main_hold_hours * 3600.0, owner))
    main = Phase("main", VoltagePolicy(_owned("main_voltage_v", manual.main_voltage_v, owner), _owned("manual_voltage_ceiling_v", safety.manual_voltage_ceiling_v, safety_owner)), CurrentPolicy(_owned("main_current_a", manual.main_current_a, owner), _owned("current_ceiling_a", safety.current_ceiling_a, safety_owner)), timers=tuple(main_timers), conditions=tuple(main_conditions))
    mix = Phase("mix", VoltagePolicy(_owned("mix_voltage_v", manual.mix_voltage_v, owner), _owned("manual_voltage_ceiling_v", safety.manual_voltage_ceiling_v, safety_owner)), CurrentPolicy(_owned("mix_current_a", manual.mix_current_a, owner), _owned("current_ceiling_a", safety.current_ceiling_a, safety_owner)), timers=(Timer("mix_hold", manual.hold_hours * 3600.0, owner), Timer("mix_authority", manual.max_mix_hours * 3600.0, owner)), conditions=(Condition("delta_voltage", f"confirmed delta-V >= {manual.delta_voltage_v:g} V", owner), Condition("delta_current", f"confirmed delta-I >= {manual.delta_current_a:g} A", owner)))
    transitions = (TransitionRule("prep", "main", "__entry__"), TransitionRule("main", "mix", "main_complete"), TransitionRule("mix", "hold", "delta_confirmed"), TransitionRule("hold", "safe_wait", "hold_complete"), TransitionRule("safe_wait", "done", "safe_wait_complete"))
    refs = (SafetyReference("temperature_limit_c", safety.temperature_limit_c), SafetyReference("telemetry_freshness_seconds", safety.telemetry_freshness_seconds))
    return ChargeProgram(f"manual:{battery.battery_id}", Mode.MANUAL, battery, battery.chemistry, (main, mix), main.voltage, main.current, main.timers + mix.timers, main.conditions + mix.conditions, refs, transitions)


__all__ = ["AUTO_PROGRAM_DEFAULTS", "ProgramDefaults", "SafetyDefaults", "auto_defaults", "build_auto_program", "build_manual_program"]
