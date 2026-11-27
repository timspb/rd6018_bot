"""Conservative HMI projection for the legacy keyboard-only compatibility call.

This uses existing ownership facts without telemetry. Action eligibility still
belongs exclusively to application/operator_button_rules via the caller.
"""
from __future__ import annotations
from typing import Any
from .hmi_state import OperatorHmiState, HmiProcessState, HmiAuthority
from .hmi_observer_runtime import _observer_runtime
from .hmi_battery_identity import _battery_label_from_observer

def compat_dashboard_state(app: Any, is_on: bool) -> OperatorHmiState:
    # Keyboard rendering itself has no live dict. Build a conservative state from
    # the known ownership/session facts; normal dashboard rendering uses full live.
    observer, observer_state = _observer_runtime(app)
    manager = getattr(app, "rd_control_mode_manager", None)
    if observer is not None and observer_state in {"active", "off_pending", "interrupted"}:
        state = OperatorHmiState(
            HmiProcessState.INTERRUPTED if observer_state == "interrupted" else HmiProcessState.ADOPTED_MIX,
            HmiAuthority.ADOPTED_MIX,
            "",
            bool(is_on),
            "—",
            _battery_label_from_observer(observer),
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "",
            "",
        )
    elif manager is not None and bool(getattr(manager, "hands_off", False)):
        state = OperatorHmiState(HmiProcessState.HANDS_OFF, HmiAuthority.EXTERNAL, "", bool(is_on), "—", "", None, None, None, None, None, None, None, "", "")
    elif bool(getattr(app.charge_controller, "is_active", False)):
        state = OperatorHmiState(HmiProcessState.RUNNING, HmiAuthority.AUTO, "", bool(is_on), "—", "", None, None, None, None, None, None, None, "", "")
    elif getattr(app, "manual_session_manager", None) is not None and bool(getattr(app.manual_session_manager, "is_active", False)):
        state = OperatorHmiState(HmiProcessState.RUNNING, HmiAuthority.MANUAL, "", bool(is_on), "—", "", None, None, None, None, None, None, None, "", "")
    else:
        state = OperatorHmiState(HmiProcessState.IDLE if not is_on else HmiProcessState.CONTAINMENT, HmiAuthority.NONE if not is_on else HmiAuthority.CONTAINMENT, "", bool(is_on), "—", "", None, None, None, None, None, None, None, "", "")
    return state
