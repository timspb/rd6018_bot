"""Test-only legacy UI parity fixtures; not a production runtime surface."""

from dataclasses import dataclass, field
from typing import Any, Mapping

from runtime.ui.models import RuntimeUISnapshot


@dataclass(frozen=True)
class LegacyUISnapshot:
    stage: str
    phase: str | None = None
    voltage: float | None = None
    current: float | None = None
    temperature: float | None = None
    timers: Mapping[str, Any] = field(default_factory=dict)
    messages: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    faults: tuple[str, ...] = ()
    battery_status: str = ""
    output_enabled: bool | None = None
    output_state: str | None = None


class LegacyUISnapshotAdapter:
    @staticmethod
    def from_mapping(data: Mapping[str, Any]) -> LegacyUISnapshot:
        def section(name: str) -> Mapping[str, Any]:
            value = data.get(name, {})
            return value if isinstance(value, Mapping) else {}

        charge, diagnostics, output = section("charge"), section("diagnostics"), section("output")
        return LegacyUISnapshot(
            stage=str(charge.get("stage", data.get("stage", "unknown"))),
            phase=None if charge.get("phase") is None else str(charge["phase"]),
            voltage=charge.get("voltage", data.get("voltage")),
            current=charge.get("current", data.get("current")),
            temperature=charge.get("temperature", data.get("temperature")),
            timers=dict(charge.get("timers", {})),
            messages=tuple(str(item) for item in charge.get("messages", ())),
            warnings=tuple(str(item) for item in diagnostics.get("warnings", data.get("warnings", ()))),
            faults=tuple(str(item) for item in diagnostics.get("faults", data.get("faults", ()))),
            battery_status=str(diagnostics.get("battery_status", data.get("battery_status", ""))),
            output_enabled=output.get("enabled", data.get("output_enabled")),
            output_state=None if output.get("state", data.get("output_state")) is None else str(output.get("state", data.get("output_state"))),
        )


@dataclass(frozen=True)
class UIParityResult:
    status: str
    matched_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    mismatches: tuple[str, ...]
    severity: str = "info"


class UIParityComparator:
    @staticmethod
    def compare(legacy: LegacyUISnapshot, v3: RuntimeUISnapshot) -> UIParityResult:
        legacy_values = {
            "stage": legacy.stage, "phase": legacy.phase, "voltage": legacy.voltage,
            "current": legacy.current, "temperature": legacy.temperature,
            "timers": legacy.timers, "messages": legacy.messages,
            "warnings": legacy.warnings, "faults": legacy.faults,
            "battery_status": legacy.battery_status, "output_enabled": legacy.output_enabled,
        }
        v3_values = {
            "stage": v3.charge.stage, "phase": v3.charge.phase,
            "voltage": v3.telemetry.voltage, "current": v3.telemetry.current,
            "temperature": v3.telemetry.temperature, "timers": v3.charge.timer_text,
            "messages": v3.journal_tail, "warnings": v3.diagnostics.reasons,
            "faults": v3.safety.violations, "battery_status": v3.diagnostics.authority,
            "output_enabled": v3.output.get("enabled"),
        }
        matched, missing, mismatches = [], [], []
        for field, expected in legacy_values.items():
            actual = v3_values[field]
            if actual is None and expected is not None:
                missing.append(field)
            elif field in {"timers", "messages", "warnings", "faults"}:
                if expected and not actual:
                    missing.append(field)
                else:
                    matched.append(field)
            elif expected == actual:
                matched.append(field)
            else:
                mismatches.append(field)
        status = "MATCH" if not missing and not mismatches else ("MISSING" if missing and not mismatches else "MISMATCH")
        severity = "error" if mismatches else ("warning" if missing else "info")
        return UIParityResult(status, tuple(matched), tuple(missing), tuple(mismatches), severity)
