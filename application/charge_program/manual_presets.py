"""Explicit V3 manual program presets; not connected to production runtime."""

from __future__ import annotations

from .models import ManualProgramInput


def requested_manual_program_input() -> ManualProgramInput:
    """Return the operator-requested MAIN -> MIX manual recipe."""

    return ManualProgramInput(
        main_voltage_v=14.1,
        main_current_a=5.0,
        main_imin_a=2.30,
        main_hold_hours=0.001,
        mix_voltage_v=15.5,
        mix_current_a=3.5,
        delta_voltage_v=0.001,
        delta_current_a=0.001,
        hold_hours=0.04,
    )


__all__ = ["requested_manual_program_input"]
