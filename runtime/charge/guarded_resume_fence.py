"""Fail-closed Output ON fence for a persisted, not-yet-adopted MAIN Guard.

This is a safety hold, NOT a Guard actuator. Before the canonical execution
owner and verified pre-ON reconciliation are installed, no bot Output ON route
may re-energize a formerly guarded session. Explicit independently owned
HANDS_OFF PSU operation is not a PB-managed charge resume.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from runtime.charge.strategy.main_guard_session import GUARD_KEY


def guarded_resume_hold(app: Any) -> bool:
    """Detect preserved Guard authority without mutating charge/session state.

    The physical runtime currently lacks the end-to-end locked readback/lease
    authority to clear this hold. It is intentionally NOT enough to find an
    in-memory restored Guard or a successful mock pre-ON classifier.
    """
    controller = getattr(app, "charge_controller", None)
    if getattr(controller, "_main_current_guard", None) is not None:
        return True
    # Respect the controller's canonical session file, not a new sidecar.
    from charge_controller import SESSION_FILE
    path = Path(getattr(app, "charge_session_file", SESSION_FILE))
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return False
    except OSError:
        # An unreadable existing canonical session cannot prove absence of an
        # earlier current cap. Fail closed; a nonexistent file is distinct.
        return True
    try:
        document = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        # Corruption in a journal-bearing file must not silently remove the
        # electrical guard. Other legacy corrupt files keep their old behavior.
        return GUARD_KEY.encode("ascii") in raw
    return isinstance(document, dict) and GUARD_KEY in document


__all__ = ["guarded_resume_hold"]
