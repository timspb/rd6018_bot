"""Metadata from real module-owned settings for native charge recipes.

Values are canonical defaults; only a documented subset is wired to pinned
session execution. Display is not evidence of active physical settings.
"""
from __future__ import annotations

from runtime.charge.programs.native_recipe_catalog import get_native_recipe
from runtime.charge.strategy import (
    main_variables, mix_variables, desulfation_variables,
    safe_wait_variables,
)
from runtime.config.variable_spec import VariableSpec


def native_recipe_parameters(recipe_id: str) -> tuple[VariableSpec, ...]:
    entry = get_native_recipe(recipe_id)
    profile = entry.profile
    main_voltage = (
        main_variables.CA_MAIN_VOLTAGE_V if profile == "Ca/Ca"
        else main_variables.EFB_MAIN_VOLTAGE_V if profile == "EFB"
        else main_variables.DEFAULT_MAIN_VOLTAGE_V
    )
    mix_voltage = (
        mix_variables.CA_MIX_VOLTAGE_V if profile == "Ca/Ca"
        else mix_variables.EFB_MIX_VOLTAGE_V if profile == "EFB"
        else mix_variables.AGM_MIX_VOLTAGE_V
    )
    tail = (
        main_variables.AGM_TAIL_HOLD_HOURS if profile == "AGM"
        else main_variables.STANDARD_TAIL_HOLD_HOURS
    )
    recovery_budget = (
        main_variables.AGM_MAX_RECOVERY_ATTEMPTS if profile == "AGM"
        else main_variables.STANDARD_MAX_RECOVERY_ATTEMPTS
    )
    specs = [
        main_voltage, main_variables.MAIN_CURRENT_C_RATE,
        main_variables.MAIN_FALLBACK_HOURS, tail, recovery_budget,
    ]
    if entry.intent != "diagnostic":
        specs += [
            desulfation_variables.DESULFATION_DURATION_HOURS,
            desulfation_variables.DESULFATION_BASE_VOLTAGE_V,
            desulfation_variables.DESULFATION_CURRENT_C_RATE,
            mix_voltage, mix_variables.MIX_CURRENT_C_RATE,
            mix_variables.MIX_FINISH_HOLD_HOURS,
        ]
    specs.extend((
        safe_wait_variables.SAFE_WAIT_MAX_HOURS,
        safe_wait_variables.SAFE_WAIT_TARGET_MARGIN_V,
    ))
    return tuple(specs)
