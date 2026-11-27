"""Lay out app-authorized actions and app-scoped ownership affordances.

This component controls presentation visibility, not callback eligibility or authority.
Only runtime.ui.telegram.renderer constructs framework markup.
"""
from __future__ import annotations

from dataclasses import replace

from application.operator_actions import OperatorAction, OperatorActionsView

from runtime.ui.labels.operator_actions import (
    AUTONOMOUS_ENTRY_BUTTON,
    AUTONOMOUS_EXIT_BUTTON,
    AUTONOMOUS_RECONCILE_BUTTON,
    MANAGED_MIX_BATTERY_BUTTON,
    MANAGED_MIX_DETAILS_BUTTON,
    MANAGED_MIX_ENTRY_BUTTON,
    MANAGED_MIX_GRAPH_BUTTON,
    MANAGED_MIX_STOP_BUTTON,
    MANAGED_ADOPTION_BUTTON,
    RD_OWNERSHIP_HANDS_OFF_BUTTON,
    RD_OWNERSHIP_RELEASE_BUTTON,
    RD_OWNERSHIP_RETURN_BUTTON,
    RD_OWNERSHIP_ADOPT_BUTTON,
    RD_OWNERSHIP_CONTAINMENT_HANDS_OFF_BUTTON,
    RD_OWNERSHIP_OUTPUT_OFF_BUTTON,
    OPERATOR_ACTION_LABELS,
)
from runtime.ui.telegram.charge import CHARGE_CALLBACK_DATA
from runtime.ui.telegram.off_conditions import OFF_CALLBACK_DATA
from runtime.ui.telegram.renderer import (
    render_callback_rows, filter_callback_markup, append_unique_callback,
)
from .hmi_state import HmiProcessState


_AUTONOMOUS_BLOCKED_CALLBACKS = {
    "rd_hands_off_disable",
    "rd_hands_off_output_off",
    "rd_managed_adopt",
    "rd_managed_mix",
    "rd_live_mix",
    "rd_ownership_adopt",
    "rd_ownership_hands_off",
    "rd_ownership_output_off",
    "rd_hands_off_release_confirm",
    "rd_autonomous_confirm",
    "charge_modes",
    CHARGE_CALLBACK_DATA,
    "v2_batteries",
    "power_toggle",
    "menu_off",
    OFF_CALLBACK_DATA,
}


def _autonomous_keyboard(app, state, markup):
    """Project only this app's autonomous coordinator into its keyboard."""
    coordinator = getattr(app, "rd_autonomous_mode", None)
    if coordinator is None:
        return markup
    manager = coordinator.manager
    if (
        not bool(getattr(state, "_output_state_known", True))
        or bool(getattr(state, "output_on", False))
    ):
        # A previously rendered keyboard must not retain autonomous controls
        # after evidence becomes unknown or Output is observed ON.
        markup = filter_callback_markup(markup, {"rd_autonomous_confirm", "rd_autonomous_exit"})
    if (
        bool(getattr(manager, "edge_autonomous", False))
        or bool(getattr(coordinator, "_entry_transition_pending", False))
        or bool(getattr(coordinator, "_entry_uncertain", False))
    ):
        markup = filter_callback_markup(markup, _AUTONOMOUS_BLOCKED_CALLBACKS)
        if bool(getattr(state, "_output_state_known", True)) and not bool(getattr(state, "output_on", False)):
            uncertain = bool(
                getattr(coordinator, "_entry_uncertain", False)
                or getattr(coordinator, "_entry_transition_pending", False)
            )
            button = AUTONOMOUS_RECONCILE_BUTTON if uncertain else AUTONOMOUS_EXIT_BUTTON
            return append_unique_callback(markup, button[0], button[1])
        return markup

    if (
        bool(getattr(manager, "pb_managed", False))
        and getattr(state, "process_state", None) is HmiProcessState.IDLE
        and bool(getattr(state, "_output_state_known", True))
        and not bool(getattr(state, "output_on", False))
    ):
        return append_unique_callback(markup, AUTONOMOUS_ENTRY_BUTTON[0], AUTONOMOUS_ENTRY_BUTTON[1])
    return markup


def _managed_adoption_keyboard(app, state, markup):
    """Add the existing D061 entry action from this app's current coordinator."""
    coordinator = getattr(app, "rd_managed_live_adoption", None)
    if (
        state.process_state is not HmiProcessState.HANDS_OFF
        or not bool(state.output_on)
        or coordinator is None
        or bool(getattr(coordinator, "active", False))
        or bool(getattr(coordinator, "off_pending", False))
    ):
        return markup
    rows = [
        [(button.text, button.callback_data) for button in row]
        for row in markup.inline_keyboard
    ]
    rows.insert(1, [MANAGED_ADOPTION_BUTTON])
    return render_callback_rows(rows)


def _mix_eligibility_keyboard(state, markup):
    """Hide impossible Mix entry actions for the supplied app's HMI projection.

    This is presentation only. The callback middleware in
    ``operator_mix_eligibility`` remains the fresh-live authorization owner.
    Import lazily because that owner imports the HMI façade's domain dependencies.
    """
    if (
        state.process_state is HmiProcessState.HANDS_OFF
        and bool(state.output_on)
    ):
        from operator_mix_eligibility import filter_non_mix_actions, potential_mix_setpoint

        if not potential_mix_setpoint(state.target_voltage_v):
            return filter_non_mix_actions(markup)
    return markup


def _managed_stop_keyboard(app, state, markup, *, actions=None):
    """Project the installed managed-stop affordance for this app only."""
    if not bool(getattr(app, "_operator_managed_stop_installed", False)) or state is None:
        return markup

    # Preserve the explicit action-view path: its declared actions already own
    # their callbacks, while a persisted orphan STOP remains independently useful.
    if actions is None:
        from operator_managed_stop import _replace_legacy_power_toggle
        markup = _replace_legacy_power_toggle(markup, state)

    from operator_managed_stop import STOP_CONFIRM_CALLBACK, _active_session_token, _orphan_stop_token
    import operator_hmi as hmi

    if (
        _active_session_token(app) is None
        and _orphan_stop_token(app) is not None
        and getattr(state, "authority", None) not in {
            hmi.HmiAuthority.AUTO,
            hmi.HmiAuthority.MANUAL,
        }
    ):
        return append_unique_callback(markup, "🛑 Завершить сохранённую сессию", STOP_CONFIRM_CALLBACK)
    return markup


def _managed_mix_keyboard(app, state, markup, *, actions=None):
    """Render D062 controls from the coordinator attached to this app only."""
    coordinator = getattr(app, "rd_managed_mix_adoption", None)
    if coordinator is None:
        return markup
    autonomous = getattr(app, "rd_autonomous_mode", None)
    if autonomous is not None and bool(getattr(autonomous.manager, "edge_autonomous", False)):
        return markup
    if bool(getattr(coordinator, "active", False)) or bool(getattr(coordinator, "off_pending", False)):
        return render_callback_rows([
            [MANAGED_MIX_STOP_BUTTON],
            [MANAGED_MIX_DETAILS_BUTTON, MANAGED_MIX_GRAPH_BUTTON],
            [MANAGED_MIX_BATTERY_BUTTON],
        ])
    if actions is not None or state.process_state is not HmiProcessState.HANDS_OFF or not state.output_on:
        return markup
    from operator_mix_eligibility import potential_mix_setpoint

    if not potential_mix_setpoint(state.target_voltage_v):
        return markup
    rows = [[(button.text, button.callback_data) for button in row] for row in markup.inline_keyboard]
    if any(callback == "rd_managed_mix" for row in rows for _label, callback in row):
        return markup
    rows.insert(1, [MANAGED_MIX_ENTRY_BUTTON])
    return render_callback_rows(rows)


def _ownership_recovery_keyboard(app, state, markup, *, actions=None):
    """Project this app's existing RD ownership state into its HMI keyboard."""
    # Merely having a control-mode manager must not expose ownership
    # affordances on an app where recovery callbacks were never registered.
    if not bool(getattr(app, "_rd_ownership_recovery_installed", False)):
        return markup
    manager = getattr(app, "rd_control_mode_manager", None)
    if manager is None or state is None:
        return markup

    controller = getattr(app, "charge_controller", None)
    manual = getattr(app, "manual_session_manager", None)
    managed_active = bool(
        (controller is not None and getattr(controller, "is_active", False))
        or (manual is not None and getattr(manual, "is_active", False))
    )

    if actions is not None:
        if state.process_state is HmiProcessState.IDLE and bool(getattr(manager, "pb_managed", False)):
            return _prepend_callback_rows(markup, [RD_OWNERSHIP_HANDS_OFF_BUTTON])
        if bool(getattr(manager, "pb_managed", False)) and managed_active:
            return _prepend_callback_rows(markup, [RD_OWNERSHIP_RELEASE_BUTTON])
        if state.process_state is HmiProcessState.HANDS_OFF and not bool(state.output_on):
            return _prepend_callback_rows(markup, [RD_OWNERSHIP_RETURN_BUTTON])
        return markup

    if state.process_state is HmiProcessState.IDLE and bool(getattr(manager, "pb_managed", False)):
        return append_unique_callback(markup, *RD_OWNERSHIP_HANDS_OFF_BUTTON)

    if (
        state.process_state is HmiProcessState.CONTAINMENT
        and bool(state.output_on)
        and bool(getattr(manager, "pb_managed", False))
        and not managed_active
    ):
        rows = []
        adoption = getattr(app, "rd_managed_live_adoption", None)
        if adoption is not None and not bool(getattr(adoption, "active", False)) and not bool(
            getattr(adoption, "off_pending", False)
        ):
            rows.append(RD_OWNERSHIP_ADOPT_BUTTON)
        rows.extend((RD_OWNERSHIP_CONTAINMENT_HANDS_OFF_BUTTON, RD_OWNERSHIP_OUTPUT_OFF_BUTTON))
        return _prepend_callback_rows(markup, rows)

    if state.process_state is HmiProcessState.HANDS_OFF and not bool(state.output_on):
        return _prepend_callback_rows(markup, [RD_OWNERSHIP_RETURN_BUTTON])
    return markup


def _prepend_callback_rows(markup, rows):
    existing = {
        str(button.callback_data or "")
        for row in markup.inline_keyboard
        for button in row
    }
    unique = [row for row in rows if row[1] not in existing]
    if not unique:
        return markup
    current = [[(button.text, button.callback_data) for button in row] for row in markup.inline_keyboard]
    return render_callback_rows([[row] for row in unique] + current)


def _panel_actions(actions, *, dark: bool):
    """Apply presentation-only visibility rules to the immutable action view."""
    if actions is None or not dark:
        return actions
    hidden = {OperatorAction.SHOW_DIAGNOSTICS}
    return replace(
        actions,
        available_actions=tuple(item for item in actions.available_actions if item.action not in hidden),
    )


def _toolbar_actions(actions):
    """Keep graph ranges and the log in the dedicated top toolbar only."""
    if actions is None:
        return None
    hidden = {OperatorAction.SHOW_GRAPH}
    return replace(
        actions,
        available_actions=tuple(item for item in actions.available_actions if item.action not in hidden),
    )


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
