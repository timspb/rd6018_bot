"""Field-level telemetry quality evaluation."""

from __future__ import annotations

import math
from typing import Any, Optional

from .models import TelemetryFieldQuality, TelemetryQualityStatus


def assess_field(
    field: str,
    value: Any,
    *,
    timestamp: Optional[float],
    now: Optional[float],
    source: Optional[str],
    max_age: Optional[float],
) -> TelemetryFieldQuality:
    if value is None:
        return TelemetryFieldQuality(field, TelemetryQualityStatus.MISSING, timestamp, None, source)
    if isinstance(value, (int, float)) and (isinstance(value, bool) or not math.isfinite(float(value))):
        return TelemetryFieldQuality(field, TelemetryQualityStatus.INVALID, timestamp, None, source)
    if timestamp is None or now is None:
        return TelemetryFieldQuality(field, TelemetryQualityStatus.INVALID, timestamp, None, source)
    age = now - timestamp
    if age < 0:
        return TelemetryFieldQuality(field, TelemetryQualityStatus.INVALID, timestamp, age, source)
    if max_age is not None and age > max_age:
        return TelemetryFieldQuality(field, TelemetryQualityStatus.STALE, timestamp, age, source)
    return TelemetryFieldQuality(field, TelemetryQualityStatus.VALID, timestamp, age, source)
