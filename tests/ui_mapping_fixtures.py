"""Test-only mapping helper for prepared UI snapshots."""

from __future__ import annotations

from typing import Any, Mapping

from runtime.ui.models import ChargeView, RuntimeUISnapshot


def snapshot_from_mapping(data: Mapping[str, Any]) -> RuntimeUISnapshot:
    charge = data.get("charge")
    if not isinstance(charge, Mapping):
        raise ValueError("legacy UI snapshot requires charge mapping")
    return RuntimeUISnapshot(
        charge=ChargeView(
            stage=str(charge.get("stage", "unknown")),
            program=str(charge.get("program", "legacy")),
            timer_text=str(charge.get("timer_text", "")),
        ),
        battery=data.get("battery", {}),
        output=data.get("output", {}),
        journal_tail=tuple(str(item) for item in data.get("journal_tail", ())),
    )
