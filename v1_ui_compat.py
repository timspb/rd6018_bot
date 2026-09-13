from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


# These callbacks are presentation/navigation surfaces.  The V1 compatibility layer
# owns their placement on the primary panel, while the wrapped V2 HMI remains the
# authority for state-specific actuator controls.
_SHELL_CALLBACKS = {
    "operator_refresh",
    "operator_details",
    "logs",
    "ai_analysis",
    "operator_more",
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

    The wrapped semantic HMI supplies the state-specific actions first (managed Stop,
    pause, HANDS_OFF containment, Mix adoption, etc.).  This layer only normalizes the
    operator-facing navigation around them:

    * Refresh / Full info;
    * Logs / AI analysis;
    * START / Modes when the semantic state is positively safe IDLE;
    * a V2/service extension entry on ordinary managed screens.

    Graph range buttons are intentionally absent here.  ``operator_dashboard`` already
    renders the V1-like 30m / 2h / Session row immediately under the graph, so adding
    them again would create duplicate controls.
    """
    del app  # Presentation composition has no runtime ownership state of its own.

    process_state = getattr(state, "process_state", None)
    authority = getattr(state, "authority", None)

    blocked = set(_SHELL_CALLBACKS)
    if process_state is hmi.HmiProcessState.IDLE:
        # Replace the current IDLE-only "Modes / Battery" layout with the V1 START /
        # Modes row.  START is deliberately routed to the V2 battery/program chooser,
        # never to the legacy raw power toggle.
        blocked.update({"charge_modes", "v2_batteries"})
    elif process_state is hmi.HmiProcessState.CONTAINMENT:
        # A containment screen is not a start surface.  Do not leave a battery chooser
        # looking like an implicit start path while physical/safety truth is unresolved.
        blocked.add("v2_batteries")

    stripped = _filter_callbacks(base, blocked)
    rows = [list(row) for row in stripped.inline_keyboard]

    # Preserve state-specific V2 controls at the top, then restore the stable V1
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

    if process_state is hmi.HmiProcessState.IDLE:
        _append_row(
            rows,
            InlineKeyboardButton(text="🚀 СТАРТ", callback_data="v2_batteries"),
            InlineKeyboardButton(text="⚙️ Режимы", callback_data="charge_modes"),
        )

    # ``Ещё`` is the additive V2 extension to the familiar V1 shell.  Keep it away
    # from ownership-special states where its submenu could advertise irrelevant or
    # stale ownership actions.  Those states retain their dedicated semantic controls.
    if process_state in {
        hmi.HmiProcessState.IDLE,
        hmi.HmiProcessState.RUNNING,
        hmi.HmiProcessState.PAUSED,
        hmi.HmiProcessState.STORAGE,
    } and authority is not hmi.HmiAuthority.CONTAINMENT:
        _append_row(
            rows,
            InlineKeyboardButton(text="🛠 Ещё", callback_data="operator_more"),
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def install_v1_ui_compat(app: Any) -> None:
    """Install V1 navigation as a presentation adapter around the semantic V2 HMI.

    Idempotence is carried by the wrapper function itself.  This adapter owns no app
    runtime state, so installing it must not widen the frozen module-as-app namespace.
    """
    del app

    import operator_hmi as hmi

    current = hmi.build_operator_keyboard
    if bool(getattr(current, "_v1_ui_compat_wrapper", False)):
        return

    original = current

    def build_keyboard(app_arg: Any, state: Any) -> InlineKeyboardMarkup:
        return compose_v1_operator_keyboard(
            app_arg,
            state,
            original(app_arg, state),
            hmi,
        )

    build_keyboard._v1_ui_compat_wrapper = True  # type: ignore[attr-defined]
    hmi.build_operator_keyboard = build_keyboard
