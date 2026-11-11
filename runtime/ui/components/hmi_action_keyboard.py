"""Layout of application-authorized operator actions for the sole Telegram renderer.

This component selects rows, not action eligibility or callback handlers.
Only runtime.ui.telegram.renderer constructs framework buttons and markup.
"""
from __future__ import annotations

from application.operator_actions import OperatorAction, OperatorActionsView
from runtime.ui.labels.operator_actions import OPERATOR_ACTION_LABELS
from runtime.ui.telegram.renderer import render_callback_rows


def _keyboard_from_actions(actions: OperatorActionsView):
    labels = OPERATOR_ACTION_LABELS
    rows: list[list[tuple[str, str]]] = []
    action_map = {item.action: item for item in actions.available_actions}
    control_actions = [
        action_map.get(OperatorAction.PAUSE_CHARGE),
        action_map.get(OperatorAction.RESUME_CHARGE),
        action_map.get(OperatorAction.STOP_CHARGE),
    ]
    control_buttons: list[tuple[str, str]] = []
    for item in control_actions:
        if item is None:
            continue
        label = labels.get(item.action)
        if label is not None:
            control_buttons.append((label[0], label[1]))
    if control_buttons:
        rows.append(control_buttons)

    manual_buttons: list[tuple[str, str]] = []
    for action in (OperatorAction.REAUTHORIZE_MANUAL, OperatorAction.DISCARD_MANUAL):
        if action in action_map:
            label = labels.get(action)
            if label is not None:
                manual_buttons.append((label[0], label[1]))
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
    # Logs and diagnostics have dedicated handlers; keep charge workspace focused.
    secondary = {OperatorAction.SHOW_LOG, OperatorAction.SHOW_DIAGNOSTICS}
    for item in actions.available_actions:
        if item.action in handled or item.action in secondary:
            continue
        label = labels.get(item.action)
        if label is not None:
            rows.append([(label[0], label[1])])
    rows.append([("🔄 Обновить", "operator_refresh")])
    return render_callback_rows(rows)
