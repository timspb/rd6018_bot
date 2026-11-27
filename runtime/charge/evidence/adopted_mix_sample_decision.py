"""Pure timestamp eligibility and SignalSample projection for adopted MIX."""

from __future__ import annotations

from rd6018_telemetry import RegulationMode
from runtime.safety.runtime_guard import RuntimeSafetyError
from signal_analyzer import SignalSample


def classify_adopted_mix_source_timestamp(
    source_timestamp_s: float | None,
    last_source_timestamp_s: float | None,
) -> bool:
    """Return whether a source timestamp is newer than the last accepted one."""
    if source_timestamp_s is None:
        raise RuntimeSafetyError("MIX_ADOPTED source timestamps unavailable")
    return last_source_timestamp_s is None or source_timestamp_s > last_source_timestamp_s


def project_adopted_mix_signal_sample(
    source_timestamp_s: float,
    voltage: float | None,
    current: float | None,
    temp: float | None,
    regulation: RegulationMode | None,
) -> SignalSample:
    """Build the analyzer sample only from a complete CV/CC U/I/T observation."""
    if (
        voltage is None
        or current is None
        or temp is None
        or regulation not in {RegulationMode.CV, RegulationMode.CC}
    ):
        raise RuntimeSafetyError("MIX_ADOPTED coherent U/I/T/CV-CC sample unavailable")
    return SignalSample(
        timestamp_s=source_timestamp_s,
        voltage_v=float(voltage),
        current_a=float(current),
        temp_c=float(temp),
        is_cv=regulation is RegulationMode.CV,
        is_cc=regulation is RegulationMode.CC,
    )


__all__ = [
    "classify_adopted_mix_source_timestamp",
    "project_adopted_mix_signal_sample",
]
