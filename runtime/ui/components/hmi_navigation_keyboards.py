"""Pure Telegram navigation keyboard layout; callbacks remain with installed handlers."""
from __future__ import annotations
from typing import Any
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from runtime.ui.telegram.analysis import ANALYSIS_CALLBACK_DATA
from .hmi_state import OperatorHmiState, HmiProcessState

def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅ К панели", callback_data="operator_done")]]
    )


def _graph_keyboard(app: Any, user_id: int) -> InlineKeyboardMarkup:
    selected = str(app._chart_range_for_user(user_id))

    def button(mode: str, text: str) -> InlineKeyboardButton:
        marker = "● " if selected == mode else ""
        return InlineKeyboardButton(text=f"{marker}{text}", callback_data=f"operator_graph_{mode}")

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                button(app.CHART_RANGE_30M, "30м"),
                button(app.CHART_RANGE_2H, "2ч"),
                button(app.CHART_RANGE_SESSION, "Сессия"),
            ],
        ]
    )
def _more_keyboard(state: OperatorHmiState) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="🧠 AI анализ", callback_data=ANALYSIS_CALLBACK_DATA)]]
    if state.process_state is HmiProcessState.IDLE:
        rows.append([InlineKeyboardButton(text="🛠 Ручной режим", callback_data="v2_manual_choose")])
        rows.append([InlineKeyboardButton(text="🔋 АКБ", callback_data="v2_batteries")])
    if state.process_state is HmiProcessState.ADOPTED_MIX:
        rows.append([InlineKeyboardButton(text="🧲 Статус Mix", callback_data="rd_live_mix_status")])
    if state.process_state is HmiProcessState.HANDS_OFF and not state.output_on:
        rows.append([InlineKeyboardButton(text="🔒 Вернуть Pb-контроль", callback_data="rd_hands_off_disable")])
    rows.append([InlineKeyboardButton(text="⬅ К панели", callback_data="operator_done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
