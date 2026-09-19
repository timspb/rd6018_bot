"""Run-local envelope for the controlled validation suite.

RD6018 is a universal lab supply.  The 0.9 A value here is deliberately not
part of the global SafetyPolicy or the production charge limits.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ControlledTestEnvelope:
    max_current_a: float = 0.9
    minimum_on_time_s: float = 10.0

    def validate(self, *, battery_voltage_v: float, voltage_v: float, current_a: float) -> None:
        if voltage_v < battery_voltage_v:
            raise ValueError("test voltage must not be below battery voltage")
        if current_a <= 0 or current_a > self.max_current_a:
            raise ValueError("test current exceeds the controlled-test envelope")


__all__ = ["ControlledTestEnvelope"]
