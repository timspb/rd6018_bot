"""Durable owner for ambiguous session-recovery quarantine incidents."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime.charge.session_atomic import atomic_session_write
from application.session_recovery_guard import RecoveryGuardState

SCHEMA_VERSION = 1
RETIREMENT_SCHEMA_VERSION = 2
OWNER = "runtime.charge.recovery_quarantine_journal"
JOURNAL_NAME = "session_recovery_quarantine.json"


class RecoveryQuarantineJournal:
    """Single persistence owner; incidents are sticky and never cleared here."""

    def __init__(self, path: str | Path, app: Any = None) -> None:
        self.path = Path(path)
        self.app = app

    def load(self) -> RecoveryGuardState:
        if not os.path.lexists(self.path):
            return RecoveryGuardState()
        try:
            with self.path.open("r", encoding="utf-8") as stream:
                document = json.load(stream)
            if not isinstance(document, dict) or document.get("owner") != OWNER:
                raise ValueError("invalid quarantine journal schema")
            version = document.get("schema_version")
            if version == RETIREMENT_SCHEMA_VERSION:
                if (set(document) != {"owner", "schema_version", "state", "quarantined", "retirement"}
                        or document.get("state") != "retired"
                        or document.get("quarantined") is not False
                        or not isinstance(document.get("retirement"), dict)):
                    raise ValueError("invalid quarantine retirement record")
                retirement = document["retirement"]
                if set(retirement) != {"operator_id", "session_id", "confirmed_off_evidence", "retired_utc", "incident_id", "incident_reason", "battery_id"}:
                    raise ValueError("invalid quarantine retirement provenance")
                if any(not isinstance(retirement.get(key), str) or not retirement[key].strip()
                       for key in ("operator_id", "session_id", "confirmed_off_evidence", "retired_utc", "incident_id", "incident_reason")):
                    raise ValueError("incomplete quarantine retirement record")
                if retirement["battery_id"] is not None and (not isinstance(retirement["battery_id"], str) or not retirement["battery_id"].strip()):
                    raise ValueError("invalid quarantine retirement battery binding")
                return RecoveryGuardState()
            if (version != SCHEMA_VERSION
                    or document.get("quarantined") is not True
                    or not isinstance(document.get("reason"), str)
                    or not document["reason"].strip()):
                raise ValueError("invalid quarantine incident schema")
            identity = document.get("identity", {})
            if not isinstance(identity, dict):
                raise ValueError("invalid quarantine journal identity")
            return RecoveryGuardState(True, document["reason"])
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            # A present but unreadable/unknown document must never be treated
            # as a fresh installation.
            return RecoveryGuardState(True, "invalid_recovery_quarantine_journal")

    def _identity(self) -> dict[str, str]:
        controller = getattr(self.app, "charge_controller", None)
        result: dict[str, str] = {}
        for key, attrs in {
            "session_id": ("_v2_trace_session_id", "session_id"),
            "battery_id": ("_v2_battery_id", "battery_id"),
        }.items():
            value = next((getattr(controller, attr, None) for attr in attrs
                          if getattr(controller, attr, None) is not None), None)
            if value is not None:
                result[key] = str(value)
        return result

    def persist(self, reason: str) -> None:
        existing = self._read_incident()
        # Preserve the original incident binding while the sticky incident is active.
        incident_id = existing.get("incident_id") if existing else str(uuid.uuid4())
        identity = existing.get("identity") if existing else self._identity()
        incident_utc = existing.get("incident_utc") if existing else datetime.now(timezone.utc).isoformat()
        incident_reason = existing.get("reason") if existing else str(reason)
        document = {
            "owner": OWNER,
            "schema_version": SCHEMA_VERSION,
            "quarantined": True,
            "reason": incident_reason,
            "incident_id": incident_id,
            "incident_utc": incident_utc,
            "identity": identity,
        }
        atomic_session_write(self.path, document, allow_nan=False)

    def retire(self, *, operator_id: str, session_id: str,
               confirmed_off_evidence: str) -> None:
        """Replace a proven incident with its bound tombstone after session retirement."""
        values = (operator_id, session_id, confirmed_off_evidence)
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("retirement requires operator, session and fresh OFF evidence")
        incident = self._read_incident()
        if incident is None:
            raise ValueError("cannot retire absent or invalid quarantine incident")
        identity = incident.get("identity")
        if (not isinstance(identity, dict) or not isinstance(identity.get("session_id"), str)
                or not identity["session_id"].strip()):
            raise ValueError("cannot retire quarantine incident without known session identity")
        if identity["session_id"].strip() != session_id.strip():
            raise ValueError("retirement session does not match quarantine incident")
        incident_id, reason = incident.get("incident_id"), incident.get("reason")
        if not isinstance(incident_id, str) or not incident_id.strip() or not isinstance(reason, str) or not reason.strip():
            raise ValueError("cannot retire quarantine incident without provenance")
        battery_id = identity.get("battery_id")
        if battery_id is not None and (not isinstance(battery_id, str) or not battery_id.strip()):
            raise ValueError("invalid quarantine incident battery identity")
        atomic_session_write(self.path, {
            "owner": OWNER,
            "schema_version": RETIREMENT_SCHEMA_VERSION,
            "state": "retired",
            "quarantined": False,
            "retirement": {
                "operator_id": operator_id.strip(),
                "session_id": session_id.strip(),
                "confirmed_off_evidence": confirmed_off_evidence.strip(),
                "retired_utc": datetime.now(timezone.utc).isoformat(),
                "incident_id": incident_id,
                "incident_reason": reason,
                "battery_id": battery_id,
            },
        }, allow_nan=False)

    def _read_incident(self) -> dict[str, Any] | None:
        """Strict schema-1 incident read used only by this persistence owner."""
        try:
            with self.path.open("r", encoding="utf-8") as stream:
                doc = json.load(stream)
            if (not isinstance(doc, dict) or doc.get("owner") != OWNER
                    or doc.get("schema_version") != SCHEMA_VERSION
                    or doc.get("quarantined") is not True
                    or not isinstance(doc.get("reason"), str) or not doc["reason"].strip()
                    or not isinstance(doc.get("incident_utc"), str) or not doc["incident_utc"].strip()
                    or not isinstance(doc.get("identity"), dict)):
                return None
            identity = doc["identity"]
            if any(not isinstance(value, str) or not value.strip() for value in identity.values()):
                return None
            return doc
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            return None


def default_journal_path() -> Path:
    # Keep the journal beside the canonical session file, without modifying it.
    from runtime.charge.persistence import SESSION_FILE
    return Path(SESSION_FILE).resolve().parent / JOURNAL_NAME


__all__ = ["JOURNAL_NAME", "OWNER", "RecoveryQuarantineJournal", "RETIREMENT_SCHEMA_VERSION", "SCHEMA_VERSION", "default_journal_path"]
