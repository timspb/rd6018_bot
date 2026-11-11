"""Read-only observation of the existing live MIX observer."""
from __future__ import annotations
from typing import Any

def _observer_runtime(app: Any) -> tuple[Any, str]:
    observer = getattr(app, "rd_live_mix_observer", None)
    if observer is None:
        return None, ""
    state = str(getattr(getattr(observer, "state", None), "value", getattr(observer, "state", "")) or "")
    return observer, state
