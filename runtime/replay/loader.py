"""Replay loaders with no transport or runtime imports."""

from __future__ import annotations

import json
from typing import Any, Mapping

from .models import ReplayScenario, TelemetryReplayRecord


def _record(data: Mapping[str, Any]) -> TelemetryReplayRecord:
    values = dict(data)
    values["timestamp"] = float(values["timestamp"])
    fields = TelemetryReplayRecord.__dataclass_fields__
    return TelemetryReplayRecord(**{
        name: values[name]
        for name in fields
        if name in values
    })


def scenario_from_mapping(data: Mapping[str, Any]) -> ReplayScenario:
    records = tuple(_record(item) for item in data.get("telemetry", ()))
    return ReplayScenario(str(data.get("scenario_id", "")), data.get("battery_profile"), data.get("recipe"), records, tuple(data.get("expected_checkpoints", ())))


def load_replay_jsonl(text: str) -> tuple[TelemetryReplayRecord, ...]:
    records = []
    for line_number, line in enumerate(str(text).splitlines(), 1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            if not isinstance(payload, Mapping):
                raise ValueError("record must be an object")
            records.append(_record(payload))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid replay record at line {line_number}") from exc
    return tuple(records)
