"""Pure timestamp projection for adopted MIX source metadata."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any


def adopted_mix_source_timestamp(live: dict[str, Any]) -> float | None:
    meta = live.get("_meta")
    if not isinstance(meta, dict):
        return None
    values: list[float] = []
    for key in (
        "current", "battery_voltage", "temp_ext_v2", "temp_ext",
        "regulation_code", "is_cv", "is_cc",
    ):
        item = meta.get(key)
        if not isinstance(item, dict):
            continue
        raw = item.get("last_reported") or item.get("last_updated")
        if not isinstance(raw, str) or not raw:
            continue
        text = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        try:
            parsed = datetime.fromisoformat(text).timestamp()
        except (ValueError, OverflowError):
            continue
        if math.isfinite(parsed) and parsed > 0:
            values.append(parsed)
    return min(values) if values else None


__all__ = ["adopted_mix_source_timestamp"]
