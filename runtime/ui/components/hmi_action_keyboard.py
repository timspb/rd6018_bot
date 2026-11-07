"""Render only application-authorized operator actions as Telegram buttons.

This file owns row layout, not eligibility, authorization or callback handlers.
"""
from __future__ import annotations
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from application.operator_actions import OperatorAction, OperatorActionsView
from runtime.ui.labels.operator_actions import OPERATOR_ACTION_LABELS

def _keyboard_from_actions(actions: OperatorActionsView) -> InlineKeyboardMarkup:
    """Render logical capabilities without reading runtime objects."""
    labels = OPERATOR_ACTION_LABELS
    rows: list[list[InlineKeyboardButton]] = []
    action_map = {item.action: item for item in actions.available_actions}
    control_actions = [
        action_map.get(OperatorAction.PAUSE_CHARGE),
        action_map.get(OperatorAction.RESUME_CHARGE),
        action_map.get(OperatorAction.STOP_CHARGE),
    ]
    control_buttons = []
    for item in control_actions:
        if item is None:
            continue
        label = labels.get(item.action)
        if label is not None:
            control_buttons.append(InlineKeyboardButton(text=label[0], callback_data=label[1]))
    if control_buttons:
        rows.append(control_buttons)
    manual_buttons = []
    for action in (OperatorAction.REAUTHORIZE_MANUAL, OperatorAction.DISCARD_MANUAL):
        if action in action_map:
            label = labels.get(action)
            if label is not None:
                manual_buttons.append(InlineKeyboardButton(text=label[0], callback_data=label[1]))
    if manual_buttons:
        rows.append(manual_buttons)
    handled = {
        OperatorAction.PAUSE_CHARGE,
        OperatorAction.RESUME_CHARGE,
        OperatorAction.STOP_CHARGE,
        OperatorAction.SHOW_GRAPH,
        OperatorAction.REAUTHORIZE_MANUAL,
        OperatorAction.DISCARD_MANUAL,
    }
    # Logs and diagnostics remain available to their dedicated handlers, but
    # are intentionally not rendered on the charge workspace.  Keep this
    # screen focused on charge control and the live readback.
    secondary = {OperatorAction.SHOW_LOG, OperatorAction.SHOW_DIAGNOSTICS}
    for item in actions.available_actions:
        if item.action in handled or item.action in secondary:
            continue
        label = labels.get(item.action)
        if label is not None:
            rows.append([InlineKeyboardButton(text=label[0], callback_data=label[1])])
    # Keep refresh as the only read-only action on the charge workspace.
    rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="operator_refresh")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
