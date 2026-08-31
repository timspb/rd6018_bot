from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional
from urllib.parse import quote


class HomeAssistantHistoryError(RuntimeError):
    """Home Assistant Recorder history could not be read or trusted."""


@dataclass(frozen=True)
class HistoryPoint:
    entity_id: str
    state: Any
    timestamp_s: float


@dataclass(frozen=True)
class NumericHistorySummary:
    entity_id: str
    count: int
    minimum: Optional[float]
    maximum: Optional[float]
    first: Optional[float]
    latest: Optional[float]


@dataclass(frozen=True)
class ContinuousOnEvidence:
    reliable: bool
    started_at_s: Optional[float]
    elapsed_s: Optional[float]
    reason: str
    points: int = 0


@dataclass(frozen=True)
class MixHistoryEvidence:
    fetched_at_s: float
    output: ContinuousOnEvidence
    current: Optional[NumericHistorySummary] = None
    output_voltage: Optional[NumericHistorySummary] = None
    battery_voltage: Optional[NumericHistorySummary] = None
    external_temperature: Optional[NumericHistorySummary] = None
    set_voltage: Optional[NumericHistorySummary] = None
    set_current: Optional[NumericHistorySummary] = None


def _parse_timestamp(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        parsed = float(value)
        return parsed if math.isfinite(parsed) and parsed > 0 else None
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed_dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed_dt.tzinfo is None:
        parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
    parsed = parsed_dt.timestamp()
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _binary(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"on", "true", "1"}:
            return True
        if normalized in {"off", "false", "0"}:
            return False
    return None


def summarize_numeric(entity_id: str, points: Iterable[HistoryPoint]) -> NumericHistorySummary:
    values = [
        value
        for point in sorted(points, key=lambda item: item.timestamp_s)
        if (value := _finite(point.state)) is not None
    ]
    if not values:
        return NumericHistorySummary(entity_id, 0, None, None, None, None)
    return NumericHistorySummary(
        entity_id=entity_id,
        count=len(values),
        minimum=min(values),
        maximum=max(values),
        first=values[0],
        latest=values[-1],
    )


def derive_continuous_on_evidence(
    points: Iterable[HistoryPoint],
    *,
    now_s: float,
    live_output_on: bool,
) -> ContinuousOnEvidence:
    """Find an explicit Recorder OFF->ON edge followed by uninterrupted known ON.

    Recorder history is useful for prior Mix *age*, but it is not silently promoted to
    chemistry evidence.  A first record that merely says ON at the beginning of the
    query window is insufficient: we require an explicit OFF state followed by ON.
    Unknown/unavailable states after that edge make the age non-authoritative.
    """

    ordered = sorted(points, key=lambda item: item.timestamp_s)
    if not live_output_on:
        return ContinuousOnEvidence(False, None, None, "live Output is not ON", len(ordered))
    if not ordered:
        return ContinuousOnEvidence(False, None, None, "Recorder returned no Output history", 0)

    previous: Optional[bool] = None
    candidate: Optional[float] = None
    ambiguous_after_candidate = False

    for point in ordered:
        state = _binary(point.state)
        if state is None:
            if candidate is not None:
                ambiguous_after_candidate = True
            previous = None
            continue
        if state is True:
            if previous is False:
                candidate = point.timestamp_s
                ambiguous_after_candidate = False
        else:
            candidate = None
            ambiguous_after_candidate = False
        previous = state

    if candidate is None:
        return ContinuousOnEvidence(
            False,
            None,
            None,
            "no explicit uninterrupted OFF->ON edge exists inside the Recorder window",
            len(ordered),
        )
    if ambiguous_after_candidate:
        return ContinuousOnEvidence(
            False,
            candidate,
            None,
            "Output history became unknown/unavailable after the detected ON edge",
            len(ordered),
        )
    elapsed = max(0.0, float(now_s) - float(candidate))
    return ContinuousOnEvidence(
        True,
        candidate,
        elapsed,
        "explicit Recorder OFF->ON edge with no later OFF/unknown state",
        len(ordered),
    )


class HomeAssistantHistoryReader:
    """Small read-only adapter for the HA `/api/history/period` Recorder endpoint."""

    def __init__(self, hass: Any, entity_map: Mapping[str, str]) -> None:
        self.hass = hass
        self.entity_map = dict(entity_map)

    async def fetch_points(
        self,
        entity_ids: Iterable[str],
        *,
        start_s: float,
        end_s: Optional[float] = None,
    ) -> dict[str, list[HistoryPoint]]:
        ids = tuple(dict.fromkeys(str(item).strip() for item in entity_ids if str(item).strip()))
        if not ids:
            return {}
        ensure_session = getattr(self.hass, "_ensure_session", None)
        base_url = str(getattr(self.hass, "base_url", "") or "").rstrip("/")
        if not callable(ensure_session) or not base_url:
            raise HomeAssistantHistoryError("Home Assistant adapter cannot read Recorder history")

        start_dt = datetime.fromtimestamp(float(start_s), tz=timezone.utc).isoformat()
        end_value = float(end_s if end_s is not None else time.time())
        end_dt = datetime.fromtimestamp(end_value, tz=timezone.utc).isoformat()
        url = f"{base_url}/api/history/period/{quote(start_dt, safe='')}"
        params = {
            "filter_entity_id": ",".join(ids),
            "end_time": end_dt,
            "no_attributes": "1",
            "significant_changes_only": "0",
        }

        try:
            session = await ensure_session()
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    raise HomeAssistantHistoryError(
                        f"Home Assistant Recorder history returned HTTP {response.status}"
                    )
                raw = await response.json()
        except HomeAssistantHistoryError:
            raise
        except Exception as exc:
            raise HomeAssistantHistoryError(
                f"Home Assistant Recorder history failed: {type(exc).__name__}: {exc}"
            ) from exc

        if not isinstance(raw, list):
            raise HomeAssistantHistoryError("Home Assistant Recorder history payload is invalid")

        result: dict[str, list[HistoryPoint]] = {entity_id: [] for entity_id in ids}
        for series_index, series in enumerate(raw):
            if not isinstance(series, list):
                continue
            fallback_entity = ids[series_index] if series_index < len(ids) else ""
            for item in series:
                if not isinstance(item, dict):
                    continue
                entity_id = str(item.get("entity_id") or fallback_entity).strip()
                if entity_id not in result:
                    continue
                timestamp = _parse_timestamp(
                    item.get("last_changed")
                    or item.get("last_updated")
                    or item.get("last_reported")
                )
                if timestamp is None:
                    continue
                result[entity_id].append(
                    HistoryPoint(
                        entity_id=entity_id,
                        state=item.get("state"),
                        timestamp_s=timestamp,
                    )
                )

        for points in result.values():
            points.sort(key=lambda item: item.timestamp_s)
        return result

    async def read_mix_evidence(
        self,
        *,
        live: Mapping[str, Any],
        lookback_s: float = 7 * 24 * 3600.0,
        now_s: Optional[float] = None,
    ) -> MixHistoryEvidence:
        now = float(now_s if now_s is not None else time.time())
        switch_entity = self.entity_map.get("switch")
        if not switch_entity:
            raise HomeAssistantHistoryError("RD6018 Output entity is not configured")

        switch_points = await self.fetch_points(
            [switch_entity],
            start_s=max(0.0, now - max(1.0, float(lookback_s))),
            end_s=now,
        )
        output = derive_continuous_on_evidence(
            switch_points.get(switch_entity, ()),
            now_s=now,
            live_output_on=_binary(live.get("switch")) is True,
        )

        telemetry_start = (
            float(output.started_at_s)
            if output.started_at_s is not None
            else max(0.0, now - min(max(1.0, float(lookback_s)), 24 * 3600.0))
        )
        keys = ("current", "voltage", "battery_voltage", "temp_ext_v2", "temp_ext", "set_voltage", "set_current")
        entity_ids = [self.entity_map[key] for key in keys if self.entity_map.get(key)]
        telemetry = await self.fetch_points(entity_ids, start_s=telemetry_start, end_s=now)

        def summary(key: str) -> Optional[NumericHistorySummary]:
            entity = self.entity_map.get(key)
            if not entity:
                return None
            return summarize_numeric(entity, telemetry.get(entity, ()))

        temp_summary = summary("temp_ext_v2")
        if temp_summary is None or temp_summary.count == 0:
            temp_summary = summary("temp_ext")

        return MixHistoryEvidence(
            fetched_at_s=now,
            output=output,
            current=summary("current"),
            output_voltage=summary("voltage"),
            battery_voltage=summary("battery_voltage"),
            external_temperature=temp_summary,
            set_voltage=summary("set_voltage"),
            set_current=summary("set_current"),
        )
