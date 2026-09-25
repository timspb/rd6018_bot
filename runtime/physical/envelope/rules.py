"""Small, pure envelope rule helpers."""

from __future__ import annotations


def within(value: float | None, lower: float, upper: float) -> bool:
    return value is not None and lower <= value <= upper


def power_within(voltage: float | None, current: float | None, maximum: float) -> bool:
    return voltage is None or current is None or voltage * current <= maximum

