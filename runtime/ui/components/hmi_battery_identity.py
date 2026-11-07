"""Read-only identity labels for adopted and manual battery sessions."""

from __future__ import annotations
from typing import Any
from .hmi_values import _finite

def _battery_label_from_observer(observer: Any) -> str:
    battery_id = str(getattr(observer, "battery_id", "") or "").strip()
    chemistry = getattr(observer, "chemistry", None)
    chemistry_text = str(getattr(chemistry, "value", chemistry) or "").strip()
    capacity = _finite(getattr(observer, "capacity_ah", None))
    pieces = [piece for piece in (battery_id, chemistry_text) if piece]
    if capacity is not None and capacity > 0:
        pieces.append(f"{capacity:g} Ah")
    return " · ".join(pieces)


def _battery_label_from_manual(manual: Any) -> str:
    """Return the selected battery identity carried by the Manual request."""
    request = getattr(manual, "request", None)
    battery_id = str(
        (getattr(request, "battery_id", "") if request is not None else "")
        or getattr(manual, "battery_id", "")
    ).strip()
    capacity = _finite(getattr(request, "capacity_ah", None) if request is not None else None)
    pieces = [battery_id] if battery_id else []
    if capacity is not None and capacity > 0:
        pieces.append(f"{capacity:g} Ah")
    return " · ".join(pieces)
