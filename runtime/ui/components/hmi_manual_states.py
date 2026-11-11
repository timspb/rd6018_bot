"""Pure projection for Manual ACTIVE and INTERRUPTED from existing manager."""
from __future__ import annotations
from typing import Any, Mapping, Callable
from manual_mode import MANUAL_MIX_FINISH_HOLD_SEC
from .hmi_state import HmiProcessState, HmiAuthority, OperatorHmiState
from .hmi_values import _duration, _finite
from .hmi_battery_identity import _battery_label_from_manual
from .manual_extrema_progress import _manual_extrema_status

def _manual_is_interrupted(app: Any) -> bool:
    manager = getattr(app, "manual_session_manager", None)
    state = getattr(getattr(manager, "state", None), "value", getattr(manager, "state", ""))
    return str(state or "").strip().lower() == "interrupted"

def manual_hmi_state(app: Any, live: Mapping[str, Any],
    *, output_on: bool, regulator: str, battery_v: float | None,
    current: float | None, power: float | None, temp_ext: float | None,
    temp_int: float | None, set_v: float | None, set_i: float | None,
    safety: str, attention: str,
    now_s: Callable[[], float],
) -> OperatorHmiState | None:
    manual = getattr(app, "manual_session_manager", None)
    if manual is not None and bool(getattr(manual, "is_active", False)):
        elapsed_s = getattr(manual, "active_elapsed_s", None)
        return OperatorHmiState(
            process_state=HmiProcessState.RUNNING,
            authority=HmiAuthority.MANUAL,
            title=f"RD6018 · {getattr(getattr(manual, 'request', None), 'operation_mode_label', 'Ручной режим')}",
            output_on=output_on,
            regulator=regulator,
            battery_label=_battery_label_from_manual(manual),
            battery_voltage_v=battery_v,
            current_a=current,
            power_w=power,
            battery_temp_c=temp_ext,
            psu_temp_c=temp_int,
            target_voltage_v=set_v,
            current_limit_a=set_i,
            # This is an internal authority label, not an operator-facing
            # transition. The panel shows the actual stage/evidence instead.
            progress="",
            safety=safety,
            attention=attention,
            stage_status=_manual_extrema_status(manual, regulator, now_s=now_s(), mix_hold_seconds=MANUAL_MIX_FINISH_HOLD_SEC),
            stage_time=_duration(elapsed_s),
            total_time=_duration(elapsed_s),
            delivered_ah=_finite(live.get("ah")),
        )

    if _manual_is_interrupted(app):
        return OperatorHmiState(
            process_state=HmiProcessState.IDLE,
            authority=HmiAuthority.NONE,
            title="RD6018 · ПРЕРВАННЫЙ ЗАРЯД",
            output_on=output_on,
            regulator=regulator,
            battery_label=_battery_label_from_manual(manual),
            battery_voltage_v=battery_v,
            current_a=current,
            power_w=power,
            battery_temp_c=temp_ext,
            psu_temp_c=temp_int,
            target_voltage_v=set_v,
            current_limit_a=set_i,
            progress="Сохранённый заряд требует авторизации или отказа",
            safety=safety,
            attention="warning",
            manual_interrupted=True,
        )
    return None
