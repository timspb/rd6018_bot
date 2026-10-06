"""Canonical managed Storage target after successful automatic completion."""

from __future__ import annotations

from dataclasses import dataclass

from runtime.config.variable_spec import ChangeEffect, OverridePolicy, VariableSpec


STORAGE_VOLTAGE_V = VariableSpec(
    key="charge.storage.voltage_v",
    default=13.8,
    value_type=float,
    unit="V",
    description="Managed Storage/float target voltage after normal automatic completion.",
    owner="runtime.charge.strategy.storage",
    provenance="accepted production Storage program",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=12.0,
    maximum=15.0,
)

STORAGE_CURRENT_A = VariableSpec(
    key="charge.storage.current_a",
    default=1.0,
    value_type=float,
    unit="A",
    description="Managed Storage current target after normal automatic completion.",
    owner="runtime.charge.strategy.storage",
    provenance="accepted production Storage program",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.1,
    maximum=12.0,
)


@dataclass(frozen=True)
class StorageTarget:
    voltage_v: float
    current_a: float


def select_storage_target() -> StorageTarget:
    return StorageTarget(
        voltage_v=float(STORAGE_VOLTAGE_V.default),
        current_a=float(STORAGE_CURRENT_A.default),
    )


__all__ = ["STORAGE_CURRENT_A", "STORAGE_VOLTAGE_V", "StorageTarget", "select_storage_target"]
