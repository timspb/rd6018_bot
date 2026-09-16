"""Read-only mapping for future V1/V3 presentation comparison."""

from __future__ import annotations

from typing import Any, Mapping

from .models import RuntimeUISnapshot


class LegacyUIAdapter:
    @staticmethod
    def snapshot_from_mapping(data: Mapping[str, Any]) -> RuntimeUISnapshot:
        """Accept a prepared legacy display snapshot; does not call UI handlers."""
        charge = data.get("charge")
        if not isinstance(charge, Mapping):
            raise ValueError("legacy UI snapshot requires charge mapping")
        from .models import ChargeView
        return RuntimeUISnapshot(
            charge=ChargeView(
                stage=str(charge.get("stage", "unknown")),
                program=str(charge.get("program", "legacy")),
                timer_text=str(charge.get("timer_text", "")),
            ),
            battery=data.get("battery", {}), output=data.get("output", {}),
            journal_tail=tuple(str(item) for item in data.get("journal_tail", ())),
        )
