"""Durable owner for ambiguous session-recovery quarantine incidents."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime.charge.session_atomic import atomic_session_write
from application.session_recovery_guard import RecoveryGuardState

SCHEMA_VERSION = 1
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
            if (not isinstance(document, dict)
                    or document.get("owner") != OWNER
                    or document.get("schema_version") != SCHEMA_VERSION
                    or document.get("quarantined") is not True
                    or not isinstance(document.get("reason"), str)
                    or not document["reason"].strip()):
                raise ValueError("invalid quarantine journal schema")
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
        document = {
            "owner": OWNER,
            "schema_version": SCHEMA_VERSION,
            "quarantined": True,
            "reason": str(reason),
            "incident_utc": datetime.now(timezone.utc).isoformat(),
            "identity": self._identity(),
        }
        atomic_session_write(self.path, document, allow_nan=False)


def default_journal_path() -> Path:
    # Keep the journal beside the canonical session file, without modifying it.
    from runtime.charge.persistence import SESSION_FILE
    return Path(SESSION_FILE).resolve().parent / JOURNAL_NAME


__all__ = ["JOURNAL_NAME", "OWNER", "RecoveryQuarantineJournal", "SCHEMA_VERSION", "default_journal_path"]
