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
        except FileNotFoundError:
            # The quarantine journal is the canonical retirement identity when
            # the controller has already removed its session document. This
            # identity is usable only while the controller is IDLE and has no
            # in-memory session; validate() rechecks the exact incident.
            controller = self.app.charge_controller
            if (getattr(controller, "current_stage", None)
                    != getattr(controller, "STAGE_IDLE", object())):
                return None
            journal = getattr(self.app, "recovery_quarantine_journal", None)
            try:
                binding = journal.incident_binding() if journal is not None else None
            except Exception:
                return None
            value = binding.get("session_id") if isinstance(binding, dict) else None
            battery_id = binding.get("battery_id") if isinstance(binding, dict) else None
            if not isinstance(value, str) or not value.strip():
                return None
            # An IDLE controller may retain the quarantined session's identity
            # in memory even though charge_session.json was removed. Accept
            # only an exact match with the immutable journal binding; reject
            # any conflicting in-memory identity.
            memory_session = getattr(controller, "_v2_trace_session_id", None)
            memory_battery = getattr(controller, "_v2_battery_id", None)
            if (memory_session is not None and memory_session != value
                    or memory_battery is not None and memory_battery != battery_id):
                return None
            return value.strip()
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
        # A partial UI controller cannot establish a persisted orphan binding.
        main = getattr(controller, "STAGE_MAIN", None)
        mix = getattr(controller, "STAGE_MIX", None)
        safe_wait = getattr(controller, "STAGE_SAFE_WAIT", None)
        idle = getattr(controller, "STAGE_IDLE", None)
        if (not all(isinstance(stage, str) and stage for stage in (main, mix, idle))
                or not isinstance(data, dict) or data.get("state") == "retired"
                or data.get("stage") not in {main, mix, safe_wait}
                or not isinstance(session_id, str) or not session_id.strip()
                or not isinstance(battery_id, str) or not battery_id.strip()
                or getattr(controller, "current_stage", controller.STAGE_IDLE) != controller.STAGE_IDLE
                or getattr(controller, "_v2_trace_session_id", None) is not None
                or getattr(controller, "_v2_battery_id", None) is not None):
            return None
        from runtime.charge.strategy.main_guard_session import GUARD_KEY, read_guard
        if GUARD_KEY not in data:
            return None
        if data["stage"] == safe_wait:
            # An abandoned final SAFE_WAIT can be retired only with the
            # existing exact session-bound continuation and history proof.
            from tools.d137_guarded_final_safe_wait import valid_guarded_final_wait
            if not valid_guarded_final_wait(data):
                return None
        if data["stage"] == controller.STAGE_MIX and not any(
            isinstance(step, dict) and step.get("from") == controller.STAGE_MAIN
            and step.get("to") == controller.STAGE_MIX
            for step in (data.get("stage_history") or [])
        ):
            return None
        try:
            guard, _ = read_guard(data, session_id=session_id,
                                 battery_id=battery_id, now_s=time.time())
        except Exception:
            return None
        if guard.pending is not None or guard.fault is not None:
            return None
        return {"session_id": session_id, "battery_id": battery_id,
                "document_sha256": hashlib.sha256(raw).hexdigest()}

    def validate(self, binding):
        controller = self.app.charge_controller
        try:
            data = self._document()
        except FileNotFoundError:
            # Authentic absent-session retirement: do not recreate a session
            # file. The strict quarantine journal identity becomes the binding;
            # OperatorRecoveryClearanceService still requires fresh Native OFF
            # evidence before journal.retire() writes its durable tombstone.
            journal = getattr(self.app, "recovery_quarantine_journal", None)
            if (getattr(controller, "current_stage", None)
                    != getattr(controller, "STAGE_IDLE", object())
                    or binding.get("document_sha256") is not None
                    or journal is None):
                return False
            try:
                incident = journal.incident_binding()
            except Exception:
                return False
            memory_session = getattr(controller, "_v2_trace_session_id", None)
            memory_battery = getattr(controller, "_v2_battery_id", None)
            return (
                incident.get("incident_id") == binding.get("incident_id")
                and incident.get("session_id") == binding.get("session_id")
                and incident.get("battery_id") == binding.get("battery_id")
                and (memory_session is None or memory_session == binding.get("session_id"))
                and (memory_battery is None or memory_battery == binding.get("battery_id"))
                and str(incident.get("reason", "")).startswith((
                    "main_guard_current_setpoint_transaction_unconfirmed:",
                    "main_guard_current_ocp_transaction_unconfirmed:",
                ))
            )
        except (OSError, ValueError, TypeError):
            return False
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
        if stage == getattr(controller, "STAGE_SAFE_WAIT", None):
            from tools.d137_guarded_final_safe_wait import valid_guarded_final_wait
            if not valid_guarded_final_wait(data):
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
                            or not str(incident.get("reason", "")).startswith((
                                "main_guard_current_setpoint_transaction_unconfirmed:",
                                "main_guard_current_ocp_transaction_unconfirmed:",  # legacy persisted incident
                            ))):
                        return False
        return True

    def retire(self, session_id, *, binding, off_evidence):
        try:
            data = self._document()
        except FileNotFoundError:
            if (binding.get("session_id") != session_id
                    or not self.validate(binding)
                    or not isinstance(off_evidence, VerifiedOffEvidence)):
                return None
            # The coordinator commits the durable journal tombstone immediately
            # after this typed receipt. No synthetic charge_session.json is made.
            return RetiredControllerSession(session_id)
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
        retired_id = getattr(controller, "_recovery_session_retired_id", None)
        if retired_id != session_id:
            # Missing-session path: finalize only after the journal has durably
            # changed to a retirement tombstone bound to this exact session.
            journal = getattr(self.app, "recovery_quarantine_journal", None)
            try:
                with journal.path.open("r", encoding="utf-8") as stream:
                    document = __import__("json").load(stream)
                retirement = document.get("retirement", {})
                committed = (
                    document.get("state") == "retired"
                    and document.get("quarantined") is False
                    and retirement.get("session_id") == session_id
                )
            except Exception:
                committed = False
            memory_session = getattr(controller, "_v2_trace_session_id", None)
            memory_battery = getattr(controller, "_v2_battery_id", None)
            retired_battery = retirement.get("battery_id") if committed else None
            if (not committed
                    or getattr(controller, "current_stage", None)
                    != getattr(controller, "STAGE_IDLE", object())
                    or (memory_session is not None and memory_session != session_id)
                    or (memory_battery is not None and memory_battery != retired_battery)):
                raise RuntimeError("session retirement identity changed before journal commit")
            # Clear only stale in-memory identity that was exactly bound to
            # the committed tombstone; never clear a conflicting live identity.
            if memory_session == session_id:
                controller._v2_trace_session_id = None
            if memory_battery == retired_battery and memory_battery is not None:
                controller._v2_battery_id = None
            controller._recovery_session_retired_id = session_id
        controller._recovery_session_retirement_pending = False
        candidate = getattr(controller, "_guarded_restore_candidate", None)
        if getattr(candidate, "session_id", None) == session_id:
            controller._guarded_restore_candidate = None


__all__ = ["_ControllerSessionRetirement"]
