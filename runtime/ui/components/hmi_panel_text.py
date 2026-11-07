"""Compact operator panel text renderer; pure, read-only, no panel publishing."""
from __future__ import annotations
import html
import re
from .hmi_state import HmiAuthority, OperatorHmiState
from .hmi_values import _finite, _value
from .hmi_compact import (
    _bold_value, _compact_transition, _compact_stage_label,
    _compact_battery_label, _compact_stage_status,
)
from runtime.ui.hmi_layout_config import PANEL_HEADING_TARGET_WIDTH, PANEL_HEADING_MIN_GAP

def render_operator_panel(state: OperatorHmiState) -> str:
    authority_value = getattr(state.authority, "value", state.authority)
    active_panel = authority_value in {
        HmiAuthority.AUTO.value,
        HmiAuthority.MANUAL.value,
        HmiAuthority.ADOPTED_MIX.value,
        HmiAuthority.AUTO,
        HmiAuthority.MANUAL,
        HmiAuthority.ADOPTED_MIX,
    }
    if active_panel:
        stage = _compact_stage_label(state)
        battery = _compact_battery_label(state.battery_label)
        transition = _compact_transition(state)
        transition_label = html.unescape(re.sub(r"<[^>]*>", "", transition)).strip()
        if authority_value == HmiAuthority.MANUAL.value or authority_value == HmiAuthority.MANUAL:
            right_label = f"РУЧНОЙ · {stage or 'MAIN'}"
        else:
            right_label = f"AUTO · {stage or 'ЗАРЯД'}"
        prefix = f"{transition_label} · " if transition_label else ""
        left_label = f"{prefix}🔋 {battery or 'ЗАРЯД'}"
        first_line = left_label + (" " * max(PANEL_HEADING_MIN_GAP, PANEL_HEADING_TARGET_WIDTH - len(left_label) - len(right_label))) + right_label
    else:
        first_line = str(state.title or "RD6018")
    lines = [f"<b>{html.escape(first_line)}</b>"]
    current_mode = html.escape(str(state.regulator or "—"))
    actual_line = (
        f"⚡ {_bold_value(state.battery_voltage_v, 2, 'V')} · "
        f"{_bold_value(state.current_a, 2, 'A')} · <b>{current_mode}</b>"
    )
    if state.target_voltage_v is not None or state.current_limit_a is not None:
        target = _value(state.target_voltage_v, 2, "V")
        limit = _value(state.current_limit_a, 2, "A")
        battery_temp = _bold_value(state.battery_temp_c, 1, "°C")
        lines.append(actual_line)
        lines.append(f"🎯 {target} · {limit} · 🌡 АКБ {battery_temp}")
    else:
        lines.append(f"{actual_line} · 🌡 АКБ {_bold_value(state.battery_temp_c, 1, '°C')}")
    stage_time = str(getattr(state, "stage_time", "") or "")
    delivered_ah = _finite(getattr(state, "delivered_ah", None))
    time_parts = []
    if stage_time:
        time_parts.append(f"⏱ {html.escape(stage_time)}")
    if delivered_ah is not None:
        time_parts.append(f"⚡ {_value(delivered_ah, 2, 'Ah')}")
    if time_parts:
        lines.append(" · ".join(time_parts))
    stage_status = _compact_stage_status(state)
    transition = _compact_transition(state)
    stage_status_warning = str(getattr(state, "stage_status", ""))
    if stage_status_warning.startswith("⚠️ Телеметрия устарела"):
        lines.append(stage_status_warning)
    else:
        next_line = stage_status if active_panel else transition or stage_status
        if not active_panel and transition and stage_status:
            next_line = f"{transition} · {stage_status.removeprefix('➡️ ')}"
        if active_panel and not next_line:
            next_line = "➡️ Ожидание условия перехода"
        if next_line:
            if next_line.startswith("➡️ <b>"):
                lines.append(next_line)
            else:
                lines.append(html.escape(next_line))
    if not active_panel:
        lines.append(f"🛡 {html.escape(state.safety.removeprefix('🛡 ').strip())}")
    return "\n".join(lines)
