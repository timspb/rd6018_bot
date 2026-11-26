"""Telegram graph-workspace keyboard layout; presentation only.

Charge ownership and action eligibility remain with existing owners.
The composed RD controls are requested once from operator_hmi so installed
ownership wrappers preserve their existing order and authority.
"""
from __future__ import annotations
from typing import Any
from aiogram.types import InlineKeyboardButton
import operator_hmi as hmi
from runtime.ui.screens.journal import journal_button_spec
from runtime.ui.telegram.renderer import render_button
from runtime.ui.components.operator_graph_policy import (
    _charge_session_active,
    _hands_off_graph_monitoring,
)

def _hide_active_release_button(markup: Any) -> Any:
    """Do not expose RD ownership transfer from the active charge workspace."""
    rows = [
        [button for button in row if button.callback_data != "rd_hands_off_release_confirm"]
        for row in markup.inline_keyboard
    ]
    return type(markup)(inline_keyboard=[row for row in rows if row])


def _graph_toolbar(app: Any, user_id: int, actions=None):
    graph_rows = hmi._graph_keyboard(app, user_id).inline_keyboard
    top_row = list(graph_rows[0]) if graph_rows else []
    if _hands_off_graph_monitoring(app) and not _charge_session_active(app) and len(top_row) >= 3:
        original = top_row[2]
        top_row[2] = InlineKeyboardButton(
            text=original.text.replace("Сессия", "24ч"),
            callback_data=original.callback_data,
        )
    if actions is not None and any(
        item.action is hmi.OperatorAction.SHOW_LOG for item in actions.available_actions
    ):
        top_row.append(render_button(journal_button_spec()))
    return top_row


def _composed_operator_rows(app: Any, state: hmi.OperatorHmiState, *, hide_active_release: bool):
    """Invoke installed ownership/adoption wrappers exactly once.

    These wrappers may extend the generic action view with RD ownership controls.
    Reuse the existing button filter without introducing another policy.
    """
    markup = hmi.build_operator_keyboard(app, state)
    # Legacy ownership/stop wrappers may add controls after the explicit
    # HMI builder has applied Output-truth. At the graph presentation
    # boundary, reapply the same fail-closed policy after all wrappers.
    from operator_output_truth import filter_keyboard_for_output_truth
    markup = filter_keyboard_for_output_truth(app, state, markup, hmi)
    if hide_active_release:
        markup = _hide_active_release_button(markup)
    return list(markup.inline_keyboard)


def _main_graph_markup(app: Any, state: hmi.OperatorHmiState, user_id: int, actions=None):
    """Render normal workspace; hide release only during managed charge."""
    return app.InlineKeyboardMarkup(
        inline_keyboard=_composed_operator_rows(app, state, hide_active_release=_charge_session_active(app))
    )


def _active_graph_panel_markup(app: Any, state: hmi.OperatorHmiState, user_id: int, actions=None):
    """Keep graph ranges and existing RD ownership controls in one message."""
    return app.InlineKeyboardMarkup(
        inline_keyboard=[_graph_toolbar(app, user_id, actions)]
        + _composed_operator_rows(app, state, hide_active_release=True)
    )
