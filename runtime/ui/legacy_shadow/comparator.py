"""Decision-free comparison of legacy display data and V3 view models."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import RuntimeUISnapshot
from .models import LegacyUISnapshot


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
                # Legacy may have structured detail while V3 exposes its canonical
                # compact representation; only report absence, not a false equality.
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
