"""Declarative operator navigation layouts; rendering stays in Telegram."""
from __future__ import annotations

from typing import Any

from runtime.ui.telegram.analysis import ANALYSIS_CALLBACK_DATA
from runtime.ui.telegram.renderer import render_callback_rows
from .hmi_state import OperatorHmiState, HmiProcessState


def _back_keyboard():
    return render_callback_rows([[("⬅ К панели", "operator_done")]])


def _graph_keyboard(app: Any, user_id: int):
    selected = str(app._chart_range_for_user(user_id))

    def button(mode: str, label: str) -> tuple[str, str]:
        marker = "● " if selected == mode else ""
        return (f"{marker}{label}", f"operator_graph_{mode}")

    return render_callback_rows([[
        button(app.CHART_RANGE_30M, "30м"),
        button(app.CHART_RANGE_2H, "2ч"),
        button(app.CHART_RANGE_SESSION, "Сессия"),
    ]])


def _more_keyboard(state: OperatorHmiState):
    rows: list[list[tuple[str, str]]] = [[("🧠 AI анализ", ANALYSIS_CALLBACK_DATA)]]
    if state.process_state is HmiProcessState.IDLE:
        rows.append([("🛠 Ручной режим", "v2_manual_choose")])
        rows.append([("🔋 АКБ", "v2_batteries")])
    if state.process_state is HmiProcessState.ADOPTED_MIX:
        rows.append([("🧲 Статус Mix", "rd_live_mix_status")])
    if state.process_state is HmiProcessState.HANDS_OFF and not state.output_on:
        rows.append([("🔒 Вернуть Pb-контроль", "rd_hands_off_disable")])
    rows.append([("⬅ К панели", "operator_done")])
    return render_callback_rows(rows)
