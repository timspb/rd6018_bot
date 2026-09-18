"""Test-only mapping helpers for already-collected hardware reports."""

from __future__ import annotations

from typing import Mapping

from runtime.output.bridge import HardwareCapability, HardwareSnapshot


def capability_from_mapping(data: Mapping[str, object]) -> HardwareCapability:
    return HardwareCapability(**{field: data[field] for field in HardwareCapability.__dataclass_fields__})


def snapshot_from_mapping(data: Mapping[str, object]) -> HardwareSnapshot:
    return HardwareSnapshot(**{field: data.get(field) for field in HardwareSnapshot.__dataclass_fields__})
