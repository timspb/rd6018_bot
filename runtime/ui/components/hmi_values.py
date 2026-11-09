"""Pure HMI value normalization and formatting, no charger authority."""

from __future__ import annotations
import math
from typing import Any, Mapping, Optional

def _finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _on(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"on", "true", "1"}


def _regulator(live: Mapping[str, Any]) -> str:
    """Project the RD6018's native regulator mode; never infer from U/I."""
    from rd6018_telemetry import resolve_regulation, RegulationMode

    mode = resolve_regulation(live)
    if mode is RegulationMode.CV:
        return "CV"
    if mode is RegulationMode.CC:
        return "CC"
    return "—"


def _temperature(value: Optional[float]) -> str:
    return "—" if value is None else f"{value:.1f}°C"


def _value(value: Optional[float], digits: int, suffix: str) -> str:
    return "—" if value is None else f"{value:.{digits}f} {suffix}"


def _duration(seconds: Any) -> str:
    value = _finite(seconds)
    if value is None:
        return "—"
    total = max(0, int(value))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}"
