"""Non-actuating, change-only provenance events for external RD6018 temperature.

Uses canonical HA/Native metadata. Does not compare temperature to a safety limit,
infer a battery temperature, change setpoints or own charging-session state.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Mapping

from rd6018_telemetry import finite_float, telemetry_freshness

logger = logging.getLogger("rd6018.temperature_journal")
TEMP_SOURCE_CHANGE_LOG_DELTA_C = 0.5  # Logging noise gate; never a thermal safety limit.


class TemperatureSourceJournalObserver:
    """Suppress duplicate source observations; retry events after failed writes."""

    def __init__(self) -> None:
        self.last_signature: tuple[Any, ...] | None = None

    def record(
        self,
        live: Mapping[str, Any],
        *,
        stage: str,
        voltage: float,
        current: float,
        temperature: Any,
        ah: float,
        session_id: str | None,
        log_event: Callable[..., Any],
    ) -> None:
        meta_root = live.get("_meta")
        meta = meta_root.get("temp_ext") if isinstance(meta_root, dict) else None
        if not isinstance(meta, dict):
            meta = {}
        value = finite_float(temperature)
        source = str(meta.get("source_key") or "unknown")
        entity_id = str(meta.get("entity_id") or "unknown")
        status = str(meta.get("status") or "unknown")
        age = finite_float(meta.get("age_s"))
        if not telemetry_freshness(live, ["temp_ext"]).valid:
            status = "stale_or_invalid"

        signature = (
            str(session_id or "session_unknown"),
            source,
            entity_id,
            status,
            round(value, 1) if value is not None else None,
        )
        prior = self.last_signature
        if prior is not None and signature[:4] == prior[:4]:
            old_value, new_value = prior[4], signature[4]
            if old_value == new_value or (
                old_value is not None and new_value is not None
                and abs(new_value - old_value) < TEMP_SOURCE_CHANGE_LOG_DELTA_C
            ):
                return

        def safe(field: str, limit: int) -> str:
            return str(field).replace("|", "/").replace("\n", " ").replace("\r", " ")[:limit]

        age_text = f"{age:.1f}" if age is not None else "unknown"
        detail = (
            f"TEMP_SOURCE | source={safe(source, 64)} | "
            f"entity_id={safe(entity_id, 128)} | status={safe(status, 32)} | "
            f"age_s={age_text}"
        )
        if value is None:
            logger.warning("%s | value unavailable", detail)
            return
        log_event(stage, voltage, current, value, ah, detail)
        self.last_signature = signature
