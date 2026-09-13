from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from rd6018_telemetry import telemetry_freshness
from v1_ui_compat import install_v1_ui_compat


OUTPUT_TRUTH_ATTR = "_output_state_known"


def _tri_state(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"on", "true", "1"}:
            return True
        if normalized in {"off", "false", "0"}:
            return False
    return None


def output_truth(live: Mapping[str, Any]) -> tuple[Optional[bool], bool]:
    """Return canonical Output value plus whether that value is fresh evidence.

    UI truth follows the same fundamental rule as actuator safety: unknown/stale is not
    proof of OFF.  The V2 readback bridge promotes the canonical Output source into the
    ``switch`` value/metadata, so this layer only needs to preserve its tri-state
    semantics instead of collapsing an unrecognized value to False.
    """
    state = _tri_state(live.get("switch"))
    try:
        fresh = bool(telemetry_freshness(live, ("switch",)).valid)
    except Exception:
        fresh = False
    known = bool(fresh and state is not None)
    return (state if known else None), known


def _managed_active(app: Any) -> bool:
    controller = getattr(app, "charge_controller", None)
    manual = getattr(app, "manual_session_manager", None)
    return bool(
        (controller is not None and getattr(controller, "is_active", False))
        or (manual is not None and getattr(manual, "is_active", False))
    )


def _mark_output_truth(state: Any, known: bool) -> Any:
    # OperatorHmiState is intentionally frozen, but an evidence annotation is not part
    # of its public constructor.  object.__setattr__ keeps compatibility with existing
    # builders while letting late composition layers distinguish UNKNOWN from OFF.
    object.__setattr__(state, OUTPUT_TRUTH_ATTR, bool(known))
    return state


def output_known(state: Any) -> bool:
    return bool(getattr(state, OUTPUT_TRUTH_ATTR, True))


def normalize_operator_state(app: Any, state: Any, live: Mapping[str, Any], hmi: Any) -> Any:
    physical, known = output_truth(live)
    if known:
        if bool(getattr(state, "output_on", False)) != bool(physical):
            state = replace(state, output_on=bool(physical))
        return _mark_output_truth(state, True)

    process_state = getattr(state, "process_state", None)
    authority = getattr(state, "authority", None)

    if process_state is hmi.HmiProcessState.HANDS_OFF:
        state = replace(
            state,
            output_on=False,
            regulator="",
            progress=(
                "Состояние Output не подтверждено · HANDS_OFF не меняет Output/V/I/OVP/OCP"
            ),
            safety="⚠️ Output state: UNKNOWN / telemetry stale",
            attention="warning",
        )
    elif not _managed_active(app) and authority not in {
        hmi.HmiAuthority.ADOPTED_MIX,
    }:
        # Without active software authority, an unknown Output must never be rendered
        # as IDLE/ready.  This is containment until fresh evidence proves ON or OFF.
        state = replace(
            state,
            process_state=hmi.HmiProcessState.CONTAINMENT,
            authority=hmi.HmiAuthority.CONTAINMENT,
            title="RD6018 · OUTPUT НЕ ПОДТВЕРЖДЁН",
            output_on=False,
            regulator="",
            progress="Физическое состояние Output неизвестно; включение новой программы заблокировано",
            safety="⚠️ Output state: UNKNOWN / telemetry stale",
            attention="alarm",
        )
    else:
        # Active managed/adopted states keep their semantic process identity, but the
        # evidence annotation makes details and action filters truthful.
        state = replace(state, output_on=False)

    return _mark_output_truth(state, False)


def _filter_callbacks(markup: InlineKeyboardMarkup, blocked: set[str]) -> InlineKeyboardMarkup:
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


def _prepend_unique(
    markup: InlineKeyboardMarkup,
    button: InlineKeyboardButton,
) -> InlineKeyboardMarkup:
    callback = str(button.callback_data or "")
    for row in markup.inline_keyboard:
        for existing in row:
            if callback and str(getattr(existing, "callback_data", "") or "") == callback:
                return markup
    return InlineKeyboardMarkup(
        inline_keyboard=[[button]] + [list(row) for row in markup.inline_keyboard]
    )


def filter_keyboard_for_output_truth(
    app: Any,
    state: Any,
    markup: InlineKeyboardMarkup,
    hmi: Any,
) -> InlineKeyboardMarkup:
    del app
    if output_known(state):
        return markup

    process_state = getattr(state, "process_state", None)
    authority = getattr(state, "authority", None)

    if process_state is hmi.HmiProcessState.HANDS_OFF:
        # Returning PB authority or adopting live output requires fresh physical state.
        # A verified operator OFF attempt is the only useful actuator resolution while
        # Output is unknown; it remains inside the existing HANDS_OFF OFF transaction.
        markup = _filter_callbacks(
            markup,
            {
                "rd_hands_off_disable",
                "rd_live_mix",
                "rd_managed_adopt",
                "rd_managed_mix",
            },
        )
        return _prepend_unique(
            markup,
            InlineKeyboardButton(
                text="⏹ Проверить / выключить Output",
                callback_data="rd_hands_off_output_off",
            ),
        )

    if process_state is hmi.HmiProcessState.CONTAINMENT:
        markup = _filter_callbacks(
            markup,
            {
                "charge_modes",
                "rd_ownership_adopt",
                "rd_ownership_hands_off",
                "rd_hands_off_disable",
                "rd_live_mix",
                "rd_managed_adopt",
                "rd_managed_mix",
            },
        )
        return _prepend_unique(
            markup,
            InlineKeyboardButton(
                text="⏹ Проверить / выключить Output",
                callback_data="rd_ownership_output_off",
            ),
        )

    if authority in {hmi.HmiAuthority.AUTO, hmi.HmiAuthority.MANUAL}:
        # Preserve the managed Stop action, but do not offer a live ownership release
        # while the physical Output state itself is not fresh/known.
        return _filter_callbacks(markup, {"rd_hands_off_release_confirm"})

    return markup


def _render_unknown_output(text: str, state: Any) -> str:
    if output_known(state):
        return text
    return (
        text.replace("Output: <b>OFF</b>", "Output: <b>UNKNOWN</b>")
        .replace("Output: <code>OFF</code>", "Output: <code>UNKNOWN</code>")
        .replace("Output: OFF ·", "Output: UNKNOWN ·")
    )


def install_operator_output_truth(app: Any) -> None:
    """Make the final production HMI preserve Output ON/OFF/UNKNOWN evidence.

    This installer must run after every semantic keyboard composition layer. It changes
    no actuator authority: callbacks continue to use their existing fresh-readback and
    verified-OFF transactions. It only prevents stale/unknown Output telemetry from
    being presented as OFF or from exposing actions whose precondition is proven OFF.

    The V1 compatibility installer is registered here, before this truth wrapper and
    the later AUTONOMOUS wrapper finish composing ``operator_hmi``. Its graph adapter
    resolves ``operator_hmi.build_operator_keyboard`` dynamically at render time, so
    the familiar shell consumes the *final filtered* V2 callback set rather than
    sitting in front of those safety filters.
    """
    if bool(getattr(app, "_operator_output_truth_installed", False)):
        return

    import operator_hmi as hmi

    # Register only the graph/dashboard presentation adapter. It deliberately leaves
    # the legacy boolean ``app._build_dashboard_keyboard`` untouched; at render time
    # its graph wrapper will call the final truth/AUTONOMOUS keyboard dynamically.
    install_v1_ui_compat(app)

    original_state_builder = hmi.build_operator_hmi_state
    original_keyboard_builder = hmi.build_operator_keyboard
    original_more_keyboard = hmi._more_keyboard
    original_details = hmi.render_operator_details
    original_service_details = hmi.render_operator_service_details

    def build_state(app_arg: Any, live: Mapping[str, Any]) -> Any:
        state = original_state_builder(app_arg, live)
        return normalize_operator_state(app_arg, state, live, hmi)

    def build_keyboard(app_arg: Any, state: Any) -> InlineKeyboardMarkup:
        markup = original_keyboard_builder(app_arg, state)
        return filter_keyboard_for_output_truth(app_arg, state, markup, hmi)

    def more_keyboard(state: Any) -> InlineKeyboardMarkup:
        markup = original_more_keyboard(state)
        if output_known(state):
            return markup
        return _filter_callbacks(markup, {"rd_hands_off_disable"})

    def render_details(app_arg: Any, state: Any, live: Mapping[str, Any]) -> str:
        return _render_unknown_output(original_details(app_arg, state, live), state)

    def render_service_details(app_arg: Any, state: Any, live: Mapping[str, Any]) -> str:
        return _render_unknown_output(original_service_details(app_arg, state, live), state)

    hmi.build_operator_hmi_state = build_state
    hmi.build_operator_keyboard = build_keyboard
    hmi._more_keyboard = more_keyboard
    hmi.render_operator_details = render_details
    hmi.render_operator_service_details = render_service_details
    app._operator_output_truth_installed = True
