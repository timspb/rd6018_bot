"""Read-only hardware capability contract."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HardwareCapability:
    supports_enable: bool
    supports_disable: bool
    min_voltage: float
    max_voltage: float
    voltage_resolution: float
    min_current: float
    max_current: float
    current_resolution: float
    supports_ovp: bool
    supports_ocp: bool
    supports_reset_protection: bool
    supports_voltage_readback: bool
    supports_current_readback: bool
    supports_output_state_readback: bool

    def __post_init__(self) -> None:
        if not (0 < self.min_voltage <= self.max_voltage and self.voltage_resolution > 0):
            raise ValueError("invalid voltage capability envelope")
        if not (0 < self.min_current <= self.max_current and self.current_resolution > 0):
            raise ValueError("invalid current capability envelope")

