"""Pure graph visibility and query selection for the operator dashboard."""
from __future__ import annotations

import time
from typing import Any


def _charge_session_active(app: Any) -> bool:
    controller = getattr(app, "charge_controller", None)
    if controller is not None and bool(getattr(controller, "is_active", False)):
        return True
    manual = getattr(app, "manual_session_manager", None)
    if manual is not None and bool(getattr(manual, "is_active", False)):
        return True
    observer = getattr(app, "rd_live_mix_observer", None)
    return observer is not None and str(getattr(observer, "state", "")) in {"active", "off_pending"}


def _hands_off_graph_monitoring(app: Any) -> bool:
    manager = getattr(app, "rd_control_mode_manager", None)
    return bool(manager is not None and getattr(manager, "hands_off", False))


def _graph_display_allowed(app: Any) -> bool:
    """Viewing saved telemetry never requires owning an active charge session."""
    return _charge_session_active(app) or _hands_off_graph_monitoring(app)


def _graph_query_params(app: Any, user_id: int):
    mode, since, limit = app._chart_query_params(user_id)
    if _hands_off_graph_monitoring(app) and not _charge_session_active(app):
        # There is no managed session start time. Offer a truthful 24h history
        # rather than calling the synthetic last-2h fallback a "session".
        if app._chart_range_for_user(user_id) == app.CHART_RANGE_SESSION:
            return app.CHART_RANGE_SESSION, time.time() - 24 * 3600, 500
    return mode, since, limit
