"""Pure admission decisions for restoring AUTO charge sessions."""

from __future__ import annotations

from typing import Any, Mapping

from runtime.charge.terminal_intent import (
    DONE_COMPLETION_STORAGE,
    DONE_OUTPUT_OFF,
    DONE_OUTPUT_ON,
)

DONE_STATE_VERSION = 1
INTERRUPTION_VERSION = 1
INTERRUPTION_OWNER = "runtime.charge.persistence"
INTERRUPTION_REASON = "process_restart"


def session_identity(document: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return stable persisted identity, projecting legacy IDs deterministically."""
    sid = document.get("v2_trace_session_id")
    started = document.get("v2_trace_started_at")
    battery = document.get("v2_battery_id")
    if isinstance(sid, str) and sid.strip():
        if "v2_battery_id" not in document:
            return None
        try:
            stamp = float(started)
        except (TypeError, ValueError, OverflowError):
            return None
        if isinstance(started, bool) or stamp != stamp or abs(stamp) == float("inf") or stamp <= 0:
            return None
        if battery is not None and not isinstance(battery, str):
            return None
        return {"session_id": sid, "started_at": stamp, "battery_id": battery}
    # Match the existing deterministic legacy trace projection without its
    # now()/host fallback. Unstable legacy documents cannot be marked.
    raw_stamp = document.get("total_start_time")
    if raw_stamp is None:
        raw_stamp = document.get("saved_at")
    try:
        stamp = float(raw_stamp)
        capacity = document.get("ah_limit")
        profile = document.get("profile")
        saved = document.get("saved_at")
        capacity_value = float(capacity)
        if (isinstance(raw_stamp, bool) or stamp != stamp or abs(stamp) == float("inf") or stamp <= 0
                or not isinstance(profile, str) or not profile
                or not isinstance(document.get("stage"), str) or not document.get("stage")
                or isinstance(capacity, bool) or capacity is None
                or capacity_value != capacity_value or abs(capacity_value) == float("inf") or capacity_value <= 0
                or not isinstance(saved, (int, float)) or isinstance(saved, bool)
                or float(saved) != float(saved) or abs(float(saved)) == float("inf")
                or float(saved) <= 0):
            return None
    except (TypeError, ValueError, OverflowError):
        return None
    uuid = __import__("uuid")
    seed = "|".join((str(profile), str(capacity), f"{stamp:.6f}", str(saved or "")))
    return {"session_id": uuid.uuid5(uuid.NAMESPACE_URL, f"rd6018-recovery:{seed}").hex,
            "started_at": stamp,
            "battery_id": battery if isinstance(battery, str) and battery else None}


def validate_interruption_marker(document: Mapping[str, Any]) -> str:
    """Classify marker as absent, valid, or blocked; malformed is never absent."""
    if "interruption_v1" not in document:
        return "absent"
    marker = document.get("interruption_v1")
    if not isinstance(marker, Mapping):
        return "blocked"
    if set(marker) != {
        "schema_version", "owner", "state", "reason", "rearmable",
        "recorded_at_utc", "session_identity",
    }:
        return "blocked"
    identity = session_identity(document)
    datetime = __import__("datetime").datetime
    try:
        recorded = datetime.fromisoformat(marker.get("recorded_at_utc", "").replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return "blocked"
    if (identity is None or marker.get("schema_version") != INTERRUPTION_VERSION
            or type(marker.get("schema_version")) is not int
            or marker.get("owner") != INTERRUPTION_OWNER
            or marker.get("state") != "interrupted"
            or marker.get("reason") != INTERRUPTION_REASON
            or marker.get("rearmable") is not False
            or not recorded.tzinfo or recorded.utcoffset() is None
            or marker.get("session_identity") != identity):
        return "blocked"
    return "interrupted"


def _explicit_storage_outcome(document: dict[str, Any]) -> bool:
    return (
        document.get("done_state_version") == DONE_STATE_VERSION
        and document.get("completion_kind") == DONE_COMPLETION_STORAGE
        and document.get("output_intent") == DONE_OUTPUT_ON
    )


def restore_allows_auto_enable(host: Any) -> bool:
    """Allow auto-enable only for active sessions or explicit managed Storage."""
    if host.current_stage == host.STAGE_DONE:
        return bool(
            getattr(host, "_done_outcome_authoritative", False)
            and getattr(host, "_done_completion_kind", None)
            == DONE_COMPLETION_STORAGE
            and getattr(host, "_done_output_intent", DONE_OUTPUT_OFF)
            == DONE_OUTPUT_ON
        )
    cooling_stage = getattr(host, "STAGE_COOLING", None)
    if cooling_stage is not None and host.current_stage == cooling_stage:
        return False
    return True
