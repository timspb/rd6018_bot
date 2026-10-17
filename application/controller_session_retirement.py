"""Application adapter for retiring a persisted controller session."""

from __future__ import annotations

import time
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
                if guard.fault is not None or guard.pending is not None:
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
        if not retire_controller_session(self.app.charge_controller, session_id=session_id,
                                         battery_id=battery_id,
                                         off_transaction_id=off_evidence.transaction_id,
                                         session_file=self.session_file):
            return None
        return RetiredControllerSession(session_id)

    def finalize(self, session_id):
        controller = self.app.charge_controller
        if getattr(controller, "_recovery_session_retired_id", None) != session_id:
            raise RuntimeError("session retirement identity changed before journal commit")
        controller._recovery_session_retirement_pending = False


__all__ = ["_ControllerSessionRetirement"]
