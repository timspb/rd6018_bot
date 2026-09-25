"""Mapping-only adapter for captured V1 display state."""

from __future__ import annotations

from typing import Any, Mapping

from .models import LegacyUISnapshot


class LegacyUISnapshotAdapter:
    @staticmethod
    def from_mapping(data: Mapping[str, Any]) -> LegacyUISnapshot:
        def section(name: str) -> Mapping[str, Any]:
            value = data.get(name, {})
            return value if isinstance(value, Mapping) else {}

        charge, diagnostics, output = section("charge"), section("diagnostics"), section("output")
        stage = str(charge.get("stage", data.get("stage", "unknown")))
        return LegacyUISnapshot(
            stage=stage,
                phase=(None if charge.get("phase") is None else str(charge["phase"])),
            voltage=charge.get("voltage", data.get("voltage")),
            current=charge.get("current", data.get("current")),
            temperature=charge.get("temperature", data.get("temperature")),
            timers=dict(charge.get("timers", {})),
            messages=tuple(str(item) for item in charge.get("messages", ())),
            warnings=tuple(str(item) for item in diagnostics.get("warnings", data.get("warnings", ()))),
            faults=tuple(str(item) for item in diagnostics.get("faults", data.get("faults", ()))),
            battery_status=str(diagnostics.get("battery_status", data.get("battery_status", ""))),
            output_enabled=output.get("enabled", data.get("output_enabled")),
            output_state=(None if output.get("state", data.get("output_state")) is None else str(output.get("state", data.get("output_state")))),
        )
