"""RD6018 event producer model and bounded local spool.

There is deliberately no network transport here. The Event Gateway API is not
published yet; EventGatewayClient is only the injectable producer-side seam.
"""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

SOURCE = "rd6018-node104"
EVENT_TYPES = frozenset({
    "charger.fault", "charger.stage_changed", "charger.mode_changed", "charger.guard_recovered", "charger.telemetry_stale",
    "charger.telemetry_unknown", "charger.telemetry_recovered",
    "charger.guard_fault", "charger.guard_state_unknown", "charger.service_down", "charger.service_recovered",
    "charger.heartbeat",
})
SEVERITIES = frozenset({"info", "warning", "critical"})
PAYLOAD_FIELDS = frozenset({
    "stage", "control_mode", "fault_code", "voltage_v", "current_a", "battery_voltage_v",
    "input_voltage_v", "configured_voltage_v", "configured_current_a", "ovp_v",
    "ocp_a", "output_state", "temperature_internal_c", "temperature_external_c",
    "freshness_s", "freshness_known", "guard_state", "service_state",
    "protection_code", "regulation_code", "autonomous_mode", "output_state_code",
    "guard_incident_at", "guard_incident_id",
})
_TEXT_FIELDS = frozenset({"stage", "control_mode", "fault_code", "guard_state", "service_state",
                         "protection_code", "regulation_code", "output_state_code",
                         "guard_incident_at", "guard_incident_id"})
_NUMBER_FIELDS = frozenset({
    "voltage_v", "current_a", "battery_voltage_v", "input_voltage_v",
    "configured_voltage_v", "configured_current_a", "ovp_v", "ocp_a",
    "temperature_internal_c", "temperature_external_c", "freshness_s",
})
_BOOL_FIELDS = frozenset({"output_state", "freshness_known", "autonomous_mode"})
_EVENT_NAMESPACE = uuid.UUID("d25834e5-f01a-4cca-884f-cc09f98abf6e")
_UTC_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$")


def _utc_timestamp(value: str) -> datetime:
    if type(value) is not str or not _UTC_RE.fullmatch(value):
        raise ValueError("occurred_at must be an RFC3339 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("invalid occurred_at timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise ValueError("occurred_at must be UTC")
    return parsed


def timestamp_utc(epoch: float) -> str:
    if type(epoch) not in (int, float) or not math.isfinite(epoch):
        raise ValueError("timestamp epoch must be finite")
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def safe_payload(value: dict[str, Any]) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError("payload must be an object")
    result: dict[str, Any] = {}
    for key, item in value.items():
        if key not in PAYLOAD_FIELDS:
            continue
        if key in _TEXT_FIELDS and type(item) is str and len(item) <= 64:
            result[key] = item
        elif key in _NUMBER_FIELDS and type(item) in (int, float) and math.isfinite(item):
            result[key] = item
        elif key in _BOOL_FIELDS and type(item) is bool:
            result[key] = item
    encoded = json.dumps(result, allow_nan=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > 2048:
        raise ValueError("payload exceeds 2048 bytes")
    return result


@dataclass(frozen=True)
class EventEnvelope:
    event_id: str
    source: str
    event_type: str
    severity: str
    occurred_at: str
    payload: dict[str, Any]
    schema_version: int = 1

    def __post_init__(self) -> None:
        try:
            parsed_id = uuid.UUID(self.event_id)
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("event_id must be a UUID") from exc
        if str(parsed_id) != self.event_id:
            raise ValueError("event_id must use canonical UUID form")
        if self.source != SOURCE:
            raise ValueError("unsupported event source")
        if self.event_type not in EVENT_TYPES:
            raise ValueError("unsupported event_type")
        if self.severity not in SEVERITIES:
            raise ValueError("unsupported severity")
        _utc_timestamp(self.occurred_at)
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("schema_version must be 1")
        if type(self.payload) is not dict or safe_payload(self.payload) != self.payload:
            raise ValueError("payload contains unsupported or invalid fields")

    def to_dict(self) -> dict[str, Any]:
        return {"event_id": self.event_id, "source": self.source,
                "event_type": self.event_type, "severity": self.severity,
                "occurred_at": self.occurred_at, "payload": dict(self.payload),
                "schema_version": self.schema_version}

    @classmethod
    def for_occurrence(cls, event_type: str, occurrence_key: str, occurred_at: float,
                       payload: dict[str, Any], severity: str = "info") -> "EventEnvelope":
        if type(occurrence_key) is not str or not occurrence_key or len(occurrence_key) > 256:
            raise ValueError("occurrence identity is required and bounded")
        event_id = str(uuid.uuid5(_EVENT_NAMESPACE, f"{SOURCE}:{event_type}:{occurrence_key}"))
        return cls(event_id, SOURCE, event_type, severity, timestamp_utc(occurred_at),
                   safe_payload(payload))


class GatewayAcceptance(str, Enum):
    ACCEPTED = "accepted"
    UNKNOWN = "unknown"


class EventGatewayClient(Protocol):
    """Proposed injectable seam, not a published Gateway network contract."""

    def submit(self, event: EventEnvelope) -> GatewayAcceptance: ...


class UnwiredEventGatewayClient:
    """Explicit fail-closed placeholder until the Gateway API is published."""

    def submit(self, event: EventEnvelope) -> GatewayAcceptance:
        raise RuntimeError("Event Gateway API contract is not published or wired")


def normalize_snapshot(raw: Any, previous: dict[str, Any] | None,
                       now: float, stale_after_s: float = 300.0) -> tuple[list[EventEnvelope], dict[str, Any]]:
    """Convert an adapter-attested typed snapshot into producer events."""
    from ha_source import SourceSnapshot
    if not isinstance(raw, SourceSnapshot) or raw.provenance != "ha102_rest_read_only_adapter":
        raise ValueError("untrusted source snapshot")
    captured = raw.captured_at
    if type(captured) not in (int, float) or not math.isfinite(captured) or captured > now + 5 or now - captured > stale_after_s:
        raise ValueError("source snapshot is stale or has invalid timestamp")
    source_values = dict(raw.values)
    stage_occurrence = source_values.get("stage_occurrence_at")
    if (type(stage_occurrence) not in (int, float) or not math.isfinite(stage_occurrence)
            or stage_occurrence <= 0 or stage_occurrence > captured + 5):
        stage_occurrence = captured
    values = safe_payload(source_values)
    current = {"stage": values.get("stage"), "fault_code": values.get("fault_code"),
               "guard_state": values.get("guard_state"), "service_state": values.get("service_state"),
               "stale": False, "freshness_unknown": False}
    prior = previous or {}
    events: list[EventEnvelope] = []

    def add(kind: str, identity: str, severity: str = "info", payload: dict[str, Any] | None = None) -> None:
        events.append(EventEnvelope.for_occurrence(kind, identity, captured,
                                                   values if payload is None else payload, severity))

    stage = current["stage"]
    if stage and prior.get("stage") and stage != prior["stage"]:
        add("charger.stage_changed", f"stage:{prior['stage']}:{stage}:{stage_occurrence}")
    if current["fault_code"] and current["fault_code"] != prior.get("fault_code"):
        add("charger.fault", f"fault:{current['fault_code']}:{stage_occurrence}", "critical")
    if current["guard_state"] in {"fault", "tripped", "quarantined"} and current["guard_state"] != prior.get("guard_state"):
        add("charger.guard_fault", f"guard:{current['guard_state']}:{stage_occurrence}", "critical")
    age = values.get("freshness_s")
    known = raw.freshness_known is True and type(age) in (int, float)
    current["stale"] = bool(known and age > stale_after_s)
    current["freshness_unknown"] = not known
    if not known and not prior.get("freshness_unknown"):
        current["source_failure_started_at"] = captured
        add("charger.telemetry_unknown", f"telemetry:unknown:{captured}", "warning", {"freshness_known": False})
    elif not known and prior.get("freshness_unknown"):
        current["source_failure_started_at"] = prior.get("source_failure_started_at", captured)
    elif known and age > stale_after_s:
        stale_since = prior.get("stale_since")
        if not prior.get("stale") or type(stale_since) not in (int, float):
            stale_since = int(round(captured - age))
        current["stale_since"] = stale_since
        if not prior.get("stale"):
            add("charger.telemetry_stale", f"telemetry:stale:{int(round(stale_since))}", "warning")
    elif known and age <= stale_after_s and (prior.get("stale") or prior.get("freshness_unknown")):
        recovery_start = prior.get("source_failure_started_at", prior.get("stale_since", captured))
        add("charger.telemetry_recovered", f"telemetry:recovered:{recovery_start}")
    return events, current


class Outbox:
    """Bounded local producer spool; it has no Dispatcher retry/ACK behavior."""
    STATES = {"pending_gateway", "gateway_accepted", "quarantined_unknown"}

    def __init__(self, path: Path, max_events: int = 1000, max_age_s: int = 7 * 86400):
        self.path, self.max_events, self.max_age_s = path, max_events, max_age_s
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=5)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, payload TEXT NOT NULL, created REAL NOT NULL, state TEXT NOT NULL DEFAULT 'pending_gateway')")
        self.db.execute("CREATE TABLE IF NOT EXISTS connector_state (state_key TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        self.db.commit()

    def enqueue(self, event: EventEnvelope, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        self.db.execute("DELETE FROM events WHERE created < ?", (now - self.max_age_s,))
        count = self.db.execute("SELECT count(*) FROM events").fetchone()[0]
        if count >= self.max_events:
            self.db.commit()
            return False
        cur = self.db.execute("INSERT OR IGNORE INTO events(event_id,payload,created) VALUES(?,?,?)",
                              (event.event_id, json.dumps(event.to_dict(), allow_nan=False), now))
        self.db.commit()
        return cur.rowcount == 1

    def pending(self, limit: int = 20) -> list[EventEnvelope]:
        rows = self.db.execute("SELECT payload FROM events WHERE state='pending_gateway' ORDER BY created LIMIT ?", (limit,)).fetchall()
        return [event_from_dict(json.loads(row[0])) for row in rows]

    def set_submission_result(self, event_id: str, result: GatewayAcceptance) -> None:
        if result is GatewayAcceptance.ACCEPTED:
            state = "gateway_accepted"
        elif result is GatewayAcceptance.UNKNOWN:
            state = "quarantined_unknown"
        else:  # Defensive against untyped injected values.
            raise TypeError("unsupported Gateway result")
        self.db.execute("UPDATE events SET state=? WHERE event_id=? AND state='pending_gateway'", (state, event_id))
        self.db.commit()

    def submit_pending_once(self, client: EventGatewayClient, limit: int = 20) -> int:
        """Single injected attempt; unknown results are quarantined, never replayed."""
        count = 0
        for event in self.pending(limit):
            result = client.submit(event)
            if not isinstance(result, GatewayAcceptance):
                raise TypeError("client must return GatewayAcceptance")
            self.set_submission_result(event.event_id, result)
            count += result is GatewayAcceptance.ACCEPTED
        return count

    def has_guard_fault_for_incident(self, fault_code: str, incident_at: str) -> bool:
        """Avoid re-alerting an already queued fault for the same still-open incident."""
        rows = self.db.execute(
            "SELECT payload FROM events WHERE state IN ('pending_gateway','gateway_accepted','quarantined_unknown')"
        ).fetchall()
        for (raw,) in rows:
            try:
                event = json.loads(raw)
                payload = event.get("payload", {})
                occurred = event.get("occurred_at", "")
                if (event.get("event_type") == "charger.guard_fault"
                        and payload.get("fault_code") == fault_code
                        and isinstance(occurred, str) and occurred >= incident_at):
                    return True
            except (TypeError, ValueError):
                continue
        return False

    def load_state(self, key: str = "previous") -> dict[str, Any] | None:
        row = self.db.execute("SELECT payload FROM connector_state WHERE state_key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def save_state(self, value: dict[str, Any], key: str = "previous") -> None:
        payload = json.dumps(value, allow_nan=False)
        self.db.execute("INSERT INTO connector_state(state_key,payload) VALUES(?,?) ON CONFLICT(state_key) DO UPDATE SET payload=excluded.payload", (key, payload))
        self.db.commit()

    def close(self) -> None:
        self.db.close()


def event_from_dict(data: dict[str, Any]) -> EventEnvelope:
    return EventEnvelope(**data)


def load_config(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("config must be a regular non-symlink file")
    if os.name == "posix" and path.stat().st_mode & 0o077:
        raise ValueError("config permissions must be 0600 or stricter")
    data = json.loads(path.read_text(encoding="utf-8"))
    allowed = {"schema", "poll_interval_s", "stale_after_s", "heartbeat_interval_s", "session_max_age_s", "entity_config", "session_path", "outbox_path", "max_events", "max_age_s"}
    if type(data) is not dict or set(data) - allowed or data.get("schema") != 1:
        raise ValueError("unsupported config schema or property")
    bounds = {"poll_interval_s": (5, 3600, 30), "stale_after_s": (30, 3600, 300), "heartbeat_interval_s": (60, 86400, 300), "session_max_age_s": (60, 604800, 86400), "max_events": (1, 10000, 1000), "max_age_s": (60, 2592000, 604800)}
    result: dict[str, Any] = {"schema": 1}
    for key, (low, high, default) in bounds.items():
        value = data.get(key, default)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{key} out of range")
        result[key] = value
    for key, default in (("entity_config", "config/physical/ha102.yaml"),
                         ("session_path", "/var/lib/rd6018-bot/charge_session.json"),
                         ("outbox_path", "./state/outbox.sqlite3")):
        value = data.get(key, default)
        if value is not None and (type(value) is not str or not value):
            raise ValueError(f"{key} must be a non-empty path")
        result[key] = value
    return result
