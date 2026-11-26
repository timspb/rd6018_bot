"""Immutable operator HMI read model; no runtime/control ownership."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional
from runtime.ui.labels.operator_actions import MANAGED_MIX_ACTIVE_TITLE, MANAGED_MIX_OFF_PENDING_TITLE

class HmiProcessState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STORAGE = "storage"
    CONTAINMENT = "containment"
    HANDS_OFF = "hands_off"
    ADOPTED_MIX = "adopted_mix"
    INTERRUPTED = "interrupted"


class HmiAuthority(str, Enum):
    NONE = "none"
    AUTO = "auto"
    MANUAL = "manual"
    EXTERNAL = "external"
    ADOPTED_MIX = "adopted_mix"
    CONTAINMENT = "containment"


@dataclass(frozen=True)
class OperatorHmiState:
    process_state: HmiProcessState
    authority: HmiAuthority
    title: str
    output_on: bool
    regulator: str
    battery_label: str
    battery_voltage_v: Optional[float]
    current_a: Optional[float]
    power_w: Optional[float]
    battery_temp_c: Optional[float]
    psu_temp_c: Optional[float]
    target_voltage_v: Optional[float]
    current_limit_a: Optional[float]
    progress: str
    safety: str
    attention: str = "normal"
    stage_status: str = ""
    finish_evidence: Optional[Mapping[str, Any]] = None
    stage_time: str = ""
    total_time: str = ""
    delivered_ah: Optional[float] = None
    manual_interrupted: bool = False


def project_managed_live_adoption_state(app: Any, state: OperatorHmiState) -> OperatorHmiState:
    """Project the current app's D061 Manual status without owning its authority."""
    from dataclasses import replace

    coordinator = getattr(app, "rd_managed_live_adoption", None)
    if (
        coordinator is not None
        and bool(getattr(coordinator, "active", False))
        and state.authority is HmiAuthority.MANUAL
    ):
        return replace(
            state,
            title="RD6018 · MANUAL ПОДХВАЧЕН",
            progress="Live adoption · исходные уставки — максимум, authority только вниз",
        )
    return state


def project_managed_mix_adoption_state(app: Any, state: OperatorHmiState) -> OperatorHmiState:
    """Project this app's current D062 coordinator into the HMI read model."""
    from dataclasses import replace
    import time

    coordinator = getattr(app, "rd_managed_mix_adoption", None)
    autonomous = getattr(app, "rd_autonomous_mode", None)
    if autonomous is not None and bool(getattr(autonomous.manager, "edge_autonomous", False)):
        return state
    if coordinator is None or not (
        bool(getattr(coordinator, "active", False))
        or bool(getattr(coordinator, "off_pending", False))
    ):
        return state

    authority = getattr(coordinator, "current_authority", None)
    battery = [str(getattr(coordinator, "battery_id", "") or "")]
    chemistry = getattr(coordinator, "chemistry", None)
    if chemistry is not None:
        battery.append(str(getattr(chemistry, "value", chemistry)))
    capacity = float(getattr(coordinator, "capacity_ah", 0) or 0)
    if capacity > 0:
        battery.append(f"{capacity:g} Ah")

    used = float(getattr(coordinator, "total_active_elapsed_s", 0) or 0) / 3600.0
    limit_s = getattr(coordinator, "hard_limit_s", None)
    limit = "?" if limit_s is None else f"{float(limit_s) / 3600.0:g}"
    if bool(getattr(coordinator, "off_pending", False)):
        progress = f"Output OFF containment · Mix budget {used:.1f}/{limit}ч"
    elif getattr(coordinator, "finish_hold_started_at_s", None) is not None:
        held = max(0.0, time.time() - float(coordinator.finish_hold_started_at_s))
        progress = f"Δ подтверждена · выдержка {held / 3600.0:.1f}/2ч · Mix {used:.1f}/{limit}ч"
    else:
        regulator = state.regulator
        criterion = "Imin → ΔI" if regulator == "CV" else ("Vmax → ΔV" if regulator == "CC" else "CV/CC Delta")
        progress = f"MIX_ADOPTED · {criterion} → 2ч → OFF · бюджет {used:.1f}/{limit}ч"

    return replace(
        state,
        process_state=HmiProcessState.ADOPTED_MIX,
        authority=HmiAuthority.ADOPTED_MIX,
        title=(MANAGED_MIX_OFF_PENDING_TITLE if bool(getattr(coordinator, "off_pending", False))
               else MANAGED_MIX_ACTIVE_TITLE),
        battery_label=" · ".join(piece for piece in battery if piece),
        target_voltage_v=float(authority.set_voltage_v) if authority is not None else state.target_voltage_v,
        current_limit_a=float(authority.set_current_a) if authority is not None else state.current_limit_a,
        progress=progress,
        attention="warning" if bool(getattr(coordinator, "off_pending", False)) else state.attention,
    )
