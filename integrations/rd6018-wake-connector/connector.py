"""Standalone read-only RD6018 event connector core.

This package deliberately has no actuator, HA write, ESP command, or bridge
completion-adapter dependency. Events remain queued until a supported producer
transport is supplied.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

ROUTE_RE = re.compile(r"^[0-9a-f]{32}$")
SECRET_RE = re.compile(r"(?i)(token|secret|password|credential|authorization|route)")
ALLOWED_TYPES = {
    "fault_alarm", "stage_transition", "telemetry_stale", "telemetry_recovered",
    "guard_lease_fault", "service_down", "service_recovered", "heartbeat",
}


def validate_route(route: object) -> str:
    if type(route) is not str or ROUTE_RE.fullmatch(route) is None:
        raise ValueError("route must be supplied externally as 32 lowercase hex characters")
    return route


def _safe_fields(value: dict[str, Any]) -> dict[str, Any]:
    # Explicit allowlist: never pass source payloads or arbitrary diagnostics through.
    allowed = {"stage", "voltage_v", "current_a", "temperature_c", "freshness_s",
               "severity", "fault_code", "service_state", "guard_state"}
    result: dict[str, Any] = {}
    for key, item in value.items():
        if key not in allowed or SECRET_RE.search(key):
            continue
        if key == "stage" and type(item) is str:
            result[key] = item[:48]
        elif key in {"fault_code", "service_state", "guard_state", "severity"} and type(item) is str:
            result[key] = item[:48]
        elif key in {"voltage_v", "current_a", "temperature_c", "freshness_s"} and type(item) in (int, float):
            result[key] = float(item)
    return result


@dataclass(frozen=True)
class Event:
    event_id: str
    event_key: str
    kind: str
    occurred_at: float
    source: str
    severity: str
    fields: dict[str, Any]

    @classmethod
    def create(cls, kind: str, key: str, occurred_at: float, source: str,
               fields: dict[str, Any], severity: str = "info") -> "Event":
        if kind not in ALLOWED_TYPES:
            raise ValueError("unsupported event kind")
        if source not in {"rd6018_readonly_diagnostic", "systemd_readonly", "connector_timer"}:
            raise ValueError("unsupported event source")
        safe_key = re.sub(r"[^A-Za-z0-9_.:-]", "_", key)[:128]
        digest = hashlib.sha256(f"rd6018-node104:{kind}:{safe_key}".encode()).hexdigest()[:32]
        return cls(digest, safe_key, kind, float(occurred_at), source,
                   severity if severity in {"info", "warning", "critical"} else "warning",
                   _safe_fields(fields))

    def payload(self) -> dict[str, Any]:
        return asdict(self)


def normalize_snapshot(raw: dict[str, Any], previous: dict[str, Any] | None,
                       now: float, stale_after_s: float = 300.0) -> tuple[list[Event], dict[str, Any]]:
    """Normalize the strict connector snapshot schema; malformed input fails closed."""
    if type(raw) is not dict or raw.get("schema") != 1:
        raise ValueError("unsupported diagnostic snapshot schema")
    captured = raw.get("captured_at")
    if type(captured) not in (int, float) or captured > now + 5 or now - captured > stale_after_s:
        raise ValueError("diagnostic snapshot is stale or has invalid timestamp")
    state = raw.get("state")
    if type(state) is not dict or type(state.get("source")) is not str:
        raise ValueError("missing typed source state")
    if state["source"] not in {"esp_native_api", "ha102_rest", "rd6018_readonly_diagnostic"}:
        raise ValueError("untrusted source marker")
    if type(state.get("values")) is not dict:
        raise ValueError("missing values")
    values = _safe_fields(state["values"])
    current = {"stage": values.get("stage"), "fault_code": values.get("fault_code"),
               "guard_state": values.get("guard_state"), "service_state": values.get("service_state")}
    prior = previous or {}
    events: list[Event] = []
    stage = current.get("stage")
    if stage and prior.get("stage") and stage != prior["stage"]:
        events.append(Event.create("stage_transition", f"{prior['stage']}->{stage}", captured,
                                   "rd6018_readonly_diagnostic", values))
    if current.get("fault_code") and current["fault_code"] != prior.get("fault_code"):
        events.append(Event.create("fault_alarm", str(current["fault_code"]), captured,
                                   "rd6018_readonly_diagnostic", values, "critical"))
    if current.get("guard_state") in {"fault", "tripped", "quarantined"} and current["guard_state"] != prior.get("guard_state"):
        events.append(Event.create("guard_lease_fault", str(current["guard_state"]), captured,
                                   "rd6018_readonly_diagnostic", values, "critical"))
    age = values.get("freshness_s")
    if type(age) in (int, float) and age > stale_after_s and not prior.get("stale"):
        events.append(Event.create("telemetry_stale", "telemetry", captured,
                                   "rd6018_readonly_diagnostic", values, "warning"))
    elif type(age) in (int, float) and age <= stale_after_s and prior.get("stale"):
        events.append(Event.create("telemetry_recovered", "telemetry", captured,
                                   "rd6018_readonly_diagnostic", values))
    return events, {**current, "stale": bool(type(age) in (int, float) and age > stale_after_s)}


class Outbox:
    def __init__(self, path: Path, max_events: int = 1000, max_age_s: int = 7 * 86400):
        self.path, self.max_events, self.max_age_s = path, max_events, max_age_s
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=5)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, event_key TEXT NOT NULL, payload TEXT NOT NULL, created REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'queued')")
        self.db.commit()

    def enqueue(self, event: Event, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        self.db.execute("DELETE FROM events WHERE created < ?", (now - self.max_age_s,))
        count = self.db.execute("SELECT count(*) FROM events").fetchone()[0]
        inserted = False
        if count < self.max_events:
            cur = self.db.execute("INSERT OR IGNORE INTO events(event_id,event_key,payload,created) VALUES(?,?,?,?)",
                                  (event.event_id, event.event_key, json.dumps(event.payload(), allow_nan=False), now))
            inserted = cur.rowcount == 1
        self.db.commit()
        return inserted

    def pending(self, now: float | None = None, limit: int = 20) -> list[dict[str, Any]]:
        now = time.time() if now is None else now
        rows = self.db.execute("SELECT event_id,payload,attempts FROM events WHERE state='queued' AND next_attempt<=? AND created>=? ORDER BY created LIMIT ?",
                               (now, now - self.max_age_s, limit)).fetchall()
        return [{"event_id": row[0], "payload": json.loads(row[1]), "attempts": row[2]} for row in rows]

    def retry_later(self, event_id: str, attempts: int, now: float | None = None) -> None:
        now = time.time() if now is None else now
        delay = min(3600, 2 ** min(attempts, 10))
        self.db.execute("UPDATE events SET attempts=attempts+1,next_attempt=? WHERE event_id=? AND state='queued'",
                        (now + delay, event_id)); self.db.commit()

    def mark_status(self, event_id: str, state: str) -> None:
        if state not in {"submitted", "acknowledged"}:
            raise ValueError("invalid delivery state")
        self.db.execute("UPDATE events SET state=? WHERE event_id=?", (state, event_id)); self.db.commit()

    def close(self) -> None:
        self.db.close()


def deliver_ready(outbox: Outbox, route: object, producer: Callable[[str, dict[str, Any]], str] | None,
                  now: float | None = None) -> int:
    """Only a supported injected producer may submit; absent/invalid route holds queue."""
    try:
        route = validate_route(route)
    except ValueError:
        return 0
    if producer is None:
        return 0
    submitted = 0
    for item in outbox.pending(now):
        try:
            status = producer(route, item["payload"])
        except Exception:
            outbox.retry_later(item["event_id"], item["attempts"] + 1, now)
            continue
        # Contract returns submitted/acknowledged explicitly; enqueue acceptance is not ACK.
        if status in {"acknowledged", "submitted"}:
            outbox.mark_status(item["event_id"], status); submitted += 1
        else:
            outbox.retry_later(item["event_id"], item["attempts"] + 1, now)
    return submitted


def load_config(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("config must be a regular non-symlink file")
    if os.name == "posix" and path.stat().st_mode & 0o077:
        raise ValueError("config permissions must be 0600 or stricter")
    data = json.loads(path.read_text(encoding="utf-8"))
    if type(data) is not dict or data.get("schema") != 1:
        raise ValueError("unsupported config schema")
    poll = data.get("poll_interval_s", 30)
    stale = data.get("stale_after_s", 300)
    heartbeat = data.get("heartbeat_interval_s", 300)
    if type(poll) is not int or not 5 <= poll <= 3600:
        raise ValueError("poll_interval_s out of range")
    if type(stale) is not int or not 30 <= stale <= 3600:
        raise ValueError("stale_after_s out of range")
    if type(heartbeat) is not int or not 60 <= heartbeat <= 86400:
        raise ValueError("heartbeat_interval_s out of range")
    route = data.get("route")
    if route is not None:
        validate_route(route)
    return {"schema": 1, "poll_interval_s": poll, "stale_after_s": stale,
            "heartbeat_interval_s": heartbeat, "route": route,
            "source_snapshot": data.get("source_snapshot"),
            "outbox_path": data.get("outbox_path", "./state/outbox.sqlite3")}
