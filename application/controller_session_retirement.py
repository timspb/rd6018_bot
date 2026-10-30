"""Application adapter for retiring a persisted controller session."""

from __future__ import annotations

import time
import hashlib
from pathlib import Path
from typing import Any

from application.operator_recovery_clearance import RetiredControllerSession, VerifiedOffEvidence
from runtime.charge.persistence import SESSION_FILE, retire_controller_session


class _ControllerSessionRetirement:
    def __init__(self, app: Any, session_file: str = SESSION_FILE) -> None:
        self.app, self.session_file = app, session_file

    def _document(self):
        import json
        with Path(self.session_file).open("r", encoding="utf-8") as stream:
            return json.load(stream)

    def session_id(self):
        try:
            data = self._document()
        except (OSError, ValueError, TypeError):
            return None
        if not isinstance(data, dict) or data.get("state") == "retired":
            return None
        value = data.get("v2_trace_session_id")
        return value.strip() if isinstance(value, str) and value.strip() else None

    def orphan_binding(self):
        """Snapshot the exact persisted MAIN document for an IDLE controller."""
        try:
            raw = Path(self.session_file).read_bytes()
            import json
            data = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeError, ValueError, TypeError):
            return None
        controller = self.app.charge_controller
        session_id = data.get("v2_trace_session_id") if isinstance(data, dict) else None
        battery_id = data.get("v2_battery_id") if isinstance(data, dict) else None
        if (not isinstance(data, dict) or data.get("state") == "retired"
                or data.get("stage") != controller.STAGE_MAIN
                or not isinstance(session_id, str) or not session_id.strip()
                or not isinstance(battery_id, str) or not battery_id.strip()
                or getattr(controller, "current_stage", controller.STAGE_IDLE) != controller.STAGE_IDLE
                or getattr(controller, "_v2_trace_session_id", None) is not None
                or getattr(controller, "_v2_battery_id", None) is not None):
            return None
        from runtime.charge.strategy.main_guard_session import GUARD_KEY
        if GUARD_KEY not in data:
            return None
        return {"session_id": session_id, "battery_id": battery_id,
                "document_sha256": hashlib.sha256(raw).hexdigest()}

    def validate(self, binding):
        try:
            data = self._document()
        except (OSError, ValueError, TypeError):
            return False
        controller = self.app.charge_controller
        session_id = self.session_id()
        if (not isinstance(data, dict) or data.get("state") == "retired"
                or not session_id or session_id != binding.get("session_id")
                or data.get("v2_battery_id") != binding.get("battery_id")
                or data.get("stage") in (None, controller.STAGE_IDLE)):
            return False
        if binding.get("document_sha256") is not None:
            try:
                if hashlib.sha256(Path(self.session_file).read_bytes()).hexdigest() != binding["document_sha256"]:
                    return False
            except OSError:
                return False
        stage = data.get("stage")
        valid_stages = {getattr(controller, name) for name in dir(controller)
                        if name.startswith("STAGE_") and isinstance(getattr(controller, name), str)}
        if stage not in valid_stages:
            return False
        current_stage = getattr(controller, "current_stage", controller.STAGE_IDLE)
        if current_stage != controller.STAGE_IDLE and (
                current_stage != stage
                or getattr(controller, "_v2_trace_session_id", None) != session_id
                or getattr(controller, "_v2_battery_id", None) != binding.get("battery_id")):
            return False
        if stage == controller.STAGE_MAIN:
            from runtime.charge.strategy.main_guard_session import GUARD_KEY, read_guard
            if GUARD_KEY in data:
                try:
                    guard, _ = read_guard(data, session_id=session_id,
                                          battery_id=binding.get("battery_id"), now_s=time.time())
                except Exception:
                    return False
                if guard.fault is not None:
                    return False
                if guard.pending is not None:
                    # The failed postflight ACK can leave a durable pending
                    # proposal. It is not authorization to resume charging.
                    # Retirement is allowed only for this exact quarantined
                    # session; the coordinator still requires fresh verified
                    # Output OFF evidence before committing retirement.
                    recovery_guard = getattr(
                        getattr(self.app, "execution_port", None),
                        "session_recovery_guard", None,
                    )
                    journal = getattr(self.app, "recovery_quarantine_journal", None)
                    if not getattr(recovery_guard, "quarantined", False) or journal is None:
                        return False
                    try:
                        incident = journal.incident_binding()
                    except Exception:
                        return False
                    if (incident.get("session_id") != session_id
                            or incident.get("battery_id") != binding.get("battery_id")
                            or incident.get("incident_id") != binding.get("incident_id")
                            or not str(incident.get("reason", "")).startswith(
                                "main_guard_current_ocp_transaction_unconfirmed:"
                            )):
                        return False
        return True

    def retire(self, session_id, *, binding, off_evidence):
        try:
            data = self._document()
        except (OSError, ValueError, TypeError):
            return None
        battery_id = data.get("v2_battery_id") if isinstance(data, dict) else None
        if (binding.get("session_id") != session_id
                or binding.get("battery_id") != battery_id
                or not self.validate(binding)
                or not isinstance(off_evidence, VerifiedOffEvidence)):
            return None
        try:
            committed = retire_controller_session(
                self.app.charge_controller, session_id=session_id,
                battery_id=battery_id,
                off_transaction_id=off_evidence.transaction_id,
                expected_document_sha256=binding.get("document_sha256"),
                session_file=self.session_file)
        except (OSError, ValueError, TypeError):
            return None
        if not committed:
            return None
        return RetiredControllerSession(session_id)

    def finalize(self, session_id):
        controller = self.app.charge_controller
        if getattr(controller, "_recovery_session_retired_id", None) != session_id:
            raise RuntimeError("session retirement identity changed before journal commit")
        controller._recovery_session_retirement_pending = False
        candidate = getattr(controller, "_guarded_restore_candidate", None)
        if getattr(candidate, "session_id", None) == session_id:
            controller._guarded_restore_candidate = None


__all__ = ["_ControllerSessionRetirement"]
