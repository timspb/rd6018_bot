from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from runtime.ui.telegram.charge import CHARGE_CALLBACK_DATA

from rd6018_telemetry import telemetry_freshness


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

    # Graph presentation may normalize a truthful projection again.
    # Preserve its explicit freshness-denial status and button restrictions.
    if getattr(state, "attention", None) == "output_unknown":
        return _mark_output_truth(replace(state, output_on=False), False)

    process_state = getattr(state, "process_state", None)
    authority = getattr(state, "authority", None)

    if process_state is hmi.HmiProcessState.HANDS_OFF:
        state = replace(
            state,
            output_on=False,
            regulator="",
            progress=(
                "Состояние Output не подтверждено · HANDS_OFF не меняет Output/V/I"
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
    # Enforce the current app's AUTONOMOUS boundary as the final renderer
    # regardless of which earlier HMI wrapper captured a semantic builder.
    from runtime.ui.components.hmi_action_keyboard import _autonomous_keyboard
    markup = _autonomous_keyboard(app, state, markup)
    autonomous = getattr(app, "rd_autonomous_mode", None)
    autonomous_boundary = bool(
        autonomous is not None
        and (
            getattr(autonomous.manager, "edge_autonomous", False)
            or getattr(autonomous, "_entry_transition_pending", False)
            or getattr(autonomous, "_entry_uncertain", False)
        )
    )
    if not output_known(state) or autonomous_boundary:
        markup = _filter_callbacks(markup, {"operator_managed_stop"})
    if output_known(state):
        if bool(getattr(state, "output_on", False)):
            return _filter_callbacks(markup, {"rd_autonomous_exit", "rd_autonomous_confirm"})
        return markup

    # Both autonomous transitions require fresh Output-OFF evidence, regardless of
    # which semantic HMI state the caller supplied.
    markup = _filter_callbacks(markup, {"rd_autonomous_exit", "rd_autonomous_confirm"})

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
                "rd_autonomous_exit",
                "rd_autonomous_confirm",
            },
        )
        autonomous = getattr(app, "rd_autonomous_mode", None)
        autonomous_boundary = bool(
            autonomous is not None
            and (
                getattr(autonomous.manager, "edge_autonomous", False)
                or getattr(autonomous, "_entry_transition_pending", False)
                or getattr(autonomous, "_entry_uncertain", False)
            )
        )
        if autonomous_boundary:
            # The explicit edge AUTONOMOUS path has no bot-originated OFF action.
            return _filter_callbacks(
                markup,
                {"rd_hands_off_output_off", "rd_ownership_output_off"},
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
                CHARGE_CALLBACK_DATA,
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
    """Retain the per-app composition marker; HMI policy runs through app-aware calls."""
    if bool(getattr(app, "_operator_output_truth_installed", False)):
        return
    app._operator_output_truth_installed = True
