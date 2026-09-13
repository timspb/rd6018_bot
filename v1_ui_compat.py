from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


# These callbacks are presentation/navigation surfaces. The V1 compatibility layer
# owns their placement on the primary panel, while the wrapped V2 HMI remains the
# authority for state-specific actuator controls.
_SHELL_CALLBACKS = {
    "operator_refresh",
    "operator_details",
    "logs",
    "ai_analysis",
    "operator_more",
}


def _callbacks(markup: InlineKeyboardMarkup) -> set[str]:
    return {
        str(getattr(button, "callback_data", "") or "")
        for row in markup.inline_keyboard
        for button in row
        if getattr(button, "callback_data", None)
    }


def _filter_callbacks(
    markup: InlineKeyboardMarkup,
    blocked: set[str],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for row in markup.inline_keyboard:
        kept = [
            button
            for button in row
            if str(getattr(button, "callback_data", "") or "") not in blocked
        ]
        if kept:
            rows.append(kept)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _append_row(
    rows: list[list[InlineKeyboardButton]],
    *buttons: InlineKeyboardButton,
) -> None:
    callbacks = {
        str(getattr(button, "callback_data", "") or "")
        for row in rows
        for button in row
    }
    unique = [
        button
        for button in buttons
        if not button.callback_data or str(button.callback_data) not in callbacks
    ]
    if unique:
        rows.append(unique)


def compose_v1_operator_keyboard(
    app: Any,
    state: Any,
    base: InlineKeyboardMarkup,
    hmi: Any,
) -> InlineKeyboardMarkup:
    """Render the familiar V1 dashboard shell without restoring V1 authority.

    ``base`` is already the *final* V2 semantic/safety keyboard. The shell therefore
    never invents actuator authority: START/Modes are restored only when the final
    keyboard itself still advertises both safe IDLE entry callbacks. Read-only V1
    navigation may be reintroduced in containment/ownership states.
    """
    del app  # No independent runtime authority is owned by this adapter.

    process_state = getattr(state, "process_state", None)
    authority = getattr(state, "authority", None)
    final_callbacks = _callbacks(base)

    # Do not resurrect an action removed by a later V2 safety/authority filter. The
    # semantic IDLE surface normally carries both callbacks; requiring both makes a
    # partially filtered surface fail closed instead of reconstructing the missing one.
    idle_authorized = {"charge_modes", "v2_batteries"}.issubset(final_callbacks)
    start_allowed = process_state is hmi.HmiProcessState.IDLE and idle_authorized

    # ``is_on=False`` is not sufficient evidence for IDLE because UNKNOWN/stale Output
    # is intentionally rendered through some legacy boolean entrypoints as false. If a
    # final V2 filter has removed either IDLE entry callback, treat the compatibility
    # shell itself as containment: no START/Modes and no additive ``More`` surface.
    shell_process_state = process_state
    shell_authority = authority
    if process_state is hmi.HmiProcessState.IDLE and not idle_authorized:
        shell_process_state = hmi.HmiProcessState.CONTAINMENT
        shell_authority = hmi.HmiAuthority.CONTAINMENT

    blocked = set(_SHELL_CALLBACKS)
    if shell_process_state is hmi.HmiProcessState.IDLE:
        blocked.update({"charge_modes", "v2_batteries"})
    elif shell_process_state is hmi.HmiProcessState.CONTAINMENT:
        blocked.update({"charge_modes", "v2_batteries"})

    stripped = _filter_callbacks(base, blocked)
    rows = [list(row) for row in stripped.inline_keyboard]

    # Preserve state-specific V2 controls first, then restore the stable V1
    # information/navigation rows around them.
    _append_row(
        rows,
        InlineKeyboardButton(text="🔄 Обновить", callback_data="operator_refresh"),
        InlineKeyboardButton(text="📋 Полная инфо", callback_data="operator_details"),
    )
    _append_row(
        rows,
        InlineKeyboardButton(text="📝 Логи", callback_data="logs"),
        InlineKeyboardButton(text="🧠 AI анализ", callback_data="ai_analysis"),
    )

    if start_allowed:
        _append_row(
            rows,
            InlineKeyboardButton(text="🚀 СТАРТ", callback_data="v2_batteries"),
            InlineKeyboardButton(text="⚙️ Режимы", callback_data="charge_modes"),
        )

    # ``Ещё`` is the additive V2 extension to the familiar V1 shell. Keep it away
    # from ownership-special states where its submenu could advertise irrelevant or
    # stale ownership actions. Those states retain their dedicated semantic controls.
    if shell_process_state in {
        hmi.HmiProcessState.IDLE,
        hmi.HmiProcessState.RUNNING,
        hmi.HmiProcessState.PAUSED,
        hmi.HmiProcessState.STORAGE,
    } and shell_authority is not hmi.HmiAuthority.CONTAINMENT:
        _append_row(
            rows,
            InlineKeyboardButton(text="🛠 Ещё", callback_data="operator_more"),
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _compose_graph_markup(
    app: Any,
    state: Any,
    base: InlineKeyboardMarkup,
    hmi: Any,
) -> InlineKeyboardMarkup:
    """Preserve the graph-range first row and apply V1 shell to panel rows only."""
    rows = list(base.inline_keyboard)
    graph_rows: list[list[InlineKeyboardButton]] = []
    panel_rows = rows
    if rows and any(
        str(getattr(button, "callback_data", "") or "").startswith("operator_graph_")
        for button in rows[0]
    ):
        graph_rows = [list(rows[0])]
        panel_rows = rows[1:]

    panel = compose_v1_operator_keyboard(
        app,
        state,
        InlineKeyboardMarkup(inline_keyboard=panel_rows),
        hmi,
    )
    return InlineKeyboardMarkup(
        inline_keyboard=graph_rows + [list(row) for row in panel.inline_keyboard]
    )


def install_v1_ui_compat(app: Any) -> None:
    """Install V1 navigation at production dashboard boundaries only.

    ``operator_hmi.build_operator_keyboard`` deliberately remains untouched. This keeps
    the semantic HMI independently testable and lets all V2 ownership/output-truth/
    AUTONOMOUS wrappers finish composing first. The dashboard shell consumes their
    final keyboard and cannot restore an action that final V2 semantics removed.
    """
    import operator_dashboard
    import operator_hmi as hmi

    dashboard_builder = getattr(app, "_build_dashboard_keyboard", None)
    if callable(dashboard_builder) and not bool(
        getattr(dashboard_builder, "_v1_ui_compat_wrapper", False)
    ):
        original_dashboard_builder = dashboard_builder

        def dashboard_keyboard(
            is_on: bool,
            user_id: int,
            *,
            back_to_dashboard: bool = False,
        ) -> InlineKeyboardMarkup:
            base = original_dashboard_builder(
                is_on,
                user_id,
                back_to_dashboard=back_to_dashboard,
            )
            if back_to_dashboard:
                return base

            # Reconstruct the same conservative semantic state used by the installed
            # operator dashboard. The final base keyboard remains the authority signal
            # for whether START/Modes may be presented.
            observer, observer_state = hmi._observer_runtime(app)
            manager = getattr(app, "rd_control_mode_manager", None)
            if observer is not None and observer_state in {"active", "off_pending", "interrupted"}:
                process = (
                    hmi.HmiProcessState.INTERRUPTED
                    if observer_state == "interrupted"
                    else hmi.HmiProcessState.ADOPTED_MIX
                )
                state = hmi.OperatorHmiState(
                    process,
                    hmi.HmiAuthority.ADOPTED_MIX,
                    "",
                    bool(is_on),
                    "—",
                    hmi._battery_label_from_observer(observer),
                    None, None, None, None, None, None, None, "", "",
                )
            elif manager is not None and bool(getattr(manager, "hands_off", False)):
                state = hmi.OperatorHmiState(
                    hmi.HmiProcessState.HANDS_OFF, hmi.HmiAuthority.EXTERNAL,
                    "", bool(is_on), "—", "", None, None, None, None, None, None, None, "", "",
                )
            elif bool(getattr(app.charge_controller, "is_active", False)):
                state = hmi.OperatorHmiState(
                    hmi.HmiProcessState.RUNNING, hmi.HmiAuthority.AUTO,
                    "", bool(is_on), "—", "", None, None, None, None, None, None, None, "", "",
                )
            elif getattr(app, "manual_session_manager", None) is not None and bool(
                getattr(app.manual_session_manager, "is_active", False)
            ):
                state = hmi.OperatorHmiState(
                    hmi.HmiProcessState.RUNNING, hmi.HmiAuthority.MANUAL,
                    "", bool(is_on), "—", "", None, None, None, None, None, None, None, "", "",
                )
            else:
                state = hmi.OperatorHmiState(
                    hmi.HmiProcessState.IDLE if not is_on else hmi.HmiProcessState.CONTAINMENT,
                    hmi.HmiAuthority.NONE if not is_on else hmi.HmiAuthority.CONTAINMENT,
                    "", bool(is_on), "—", "", None, None, None, None, None, None, None, "", "",
                )
            return compose_v1_operator_keyboard(app, state, base, hmi)

        dashboard_keyboard._v1_ui_compat_wrapper = True  # type: ignore[attr-defined]
        app._build_dashboard_keyboard = dashboard_keyboard

    graph_builder = operator_dashboard._main_graph_markup
    if not bool(getattr(graph_builder, "_v1_ui_compat_wrapper", False)):
        original_graph_builder = graph_builder

        def main_graph_markup(app_arg: Any, state: Any, user_id: int) -> InlineKeyboardMarkup:
            base = original_graph_builder(app_arg, state, user_id)
            return _compose_graph_markup(app_arg, state, base, hmi)

        main_graph_markup._v1_ui_compat_wrapper = True  # type: ignore[attr-defined]
        operator_dashboard._main_graph_markup = main_graph_markup
