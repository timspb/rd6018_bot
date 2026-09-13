from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


# These callbacks are presentation/navigation surfaces. The V1 compatibility layer
# owns their placement on the primary graph panel, while the wrapped V2 HMI remains
# the authority for state-specific actuator controls.
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
    """Render the familiar V1 shell around an already-final V2 keyboard.

    ``base`` must come from the truthful production graph/dashboard path. The shell
    never invents actuator authority: START/Modes are restored only when the final V2
    keyboard still advertises both safe IDLE entry callbacks. Read-only V1 navigation
    may be reintroduced in containment/ownership states.
    """
    del app

    process_state = getattr(state, "process_state", None)
    authority = getattr(state, "authority", None)
    final_callbacks = _callbacks(base)

    idle_authorized = {"charge_modes", "v2_batteries"}.issubset(final_callbacks)
    start_allowed = process_state is hmi.HmiProcessState.IDLE and idle_authorized

    shell_process_state = process_state
    shell_authority = authority
    if process_state is hmi.HmiProcessState.IDLE and not idle_authorized:
        shell_process_state = hmi.HmiProcessState.CONTAINMENT
        shell_authority = hmi.HmiAuthority.CONTAINMENT

    blocked = set(_SHELL_CALLBACKS)
    if shell_process_state in {
        hmi.HmiProcessState.IDLE,
        hmi.HmiProcessState.CONTAINMENT,
    }:
        blocked.update({"charge_modes", "v2_batteries"})

    stripped = _filter_callbacks(base, blocked)
    rows = [list(row) for row in stripped.inline_keyboard]

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
    """Install V1 navigation on the truthful production graph panel only.

    The legacy ``app._build_dashboard_keyboard(is_on: bool, ...)`` is intentionally not
    wrapped: its boolean cannot distinguish confirmed OFF from stale/UNKNOWN Output.
    ``operator_dashboard._main_graph_markup`` receives an HMI state derived from the
    fresh live snapshot and dynamically calls the fully composed V2 keyboard, including
    Output-truth and AUTONOMOUS filters. The V1 shell consumes that final result and
    therefore cannot manufacture a filtered actuator capability.
    """
    del app

    import operator_dashboard
    import operator_hmi as hmi

    graph_builder = operator_dashboard._main_graph_markup
    if bool(getattr(graph_builder, "_v1_ui_compat_wrapper", False)):
        return

    original_graph_builder = graph_builder

    def main_graph_markup(app_arg: Any, state: Any, user_id: int) -> InlineKeyboardMarkup:
        base = original_graph_builder(app_arg, state, user_id)
        return _compose_graph_markup(app_arg, state, base, hmi)

    main_graph_markup._v1_ui_compat_wrapper = True  # type: ignore[attr-defined]
    operator_dashboard._main_graph_markup = main_graph_markup
