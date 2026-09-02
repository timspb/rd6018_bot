from __future__ import annotations

from typing import Any, Mapping

from aiogram.types import InlineKeyboardMarkup

from pb_domain import BatteryChemistry
from rd6018_telemetry import finite_float
from rd_live_adoption import MIX_HARD_LIMIT_HOURS
from rd_managed_mix import ADOPTED_MIX_SETPOINT_TOLERANCE
from recipe_engine import POLICIES


MIX_ENTRY_CALLBACKS = frozenset({"rd_live_mix", "rd_managed_mix"})

# Before the operator selects a physical battery we cannot apply the chemistry-specific
# D062 envelope. We can still prove that a setpoint is *not* Mix for every supported
# chemistry. The lowest accepted high-voltage boundary is Ca/Ca normal ceiling + the
# same tolerance used by D062. Anything at/below this boundary must not be presented
# as a Mix action.
POTENTIAL_MIX_MIN_SETPOINT_V = min(
    POLICIES[chemistry].normal_voltage_ceiling_v + ADOPTED_MIX_SETPOINT_TOLERANCE
    for chemistry in MIX_HARD_LIMIT_HOURS
    if chemistry is not BatteryChemistry.CUSTOM and chemistry in POLICIES
)


def potential_mix_setpoint(value: Any) -> bool:
    parsed = finite_float(value)
    return bool(
        parsed is not None
        and parsed > float(POTENTIAL_MIX_MIN_SETPOINT_V) + 1e-9
    )


def potential_mix_live(live: Mapping[str, Any]) -> bool:
    return potential_mix_setpoint(live.get("set_voltage"))


def filter_non_mix_actions(markup: InlineKeyboardMarkup) -> InlineKeyboardMarkup:
    rows = []
    for row in markup.inline_keyboard:
        kept = [
            button
            for button in row
            if button.callback_data not in MIX_ENTRY_CALLBACKS
        ]
        if kept:
            rows.append(kept)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def install_mix_action_eligibility(app: Any) -> None:
    """Hide and non-bypassably gate Mix entry actions for obvious non-Mix programs.

    Chemistry-specific D062 validation still happens after the physical battery is
    selected. This layer only removes the impossible generic case that was exposed by
    the physical D061 test: e.g. HANDS_OFF + Output ON at 13.60 V is ordinary external
    charging/manual power, not an external Mix.
    """

    if bool(getattr(app, "_mix_action_eligibility_installed", False)):
        return

    import operator_hmi

    original_keyboard = operator_hmi.build_operator_keyboard

    def build_keyboard(app_arg: Any, state: Any) -> InlineKeyboardMarkup:
        markup = original_keyboard(app_arg, state)
        if (
            state.process_state is operator_hmi.HmiProcessState.HANDS_OFF
            and bool(state.output_on)
            and not potential_mix_setpoint(state.target_voltage_v)
        ):
            return filter_non_mix_actions(markup)
        return markup

    operator_hmi.build_operator_keyboard = build_keyboard

    async def entry_gate(handler: Any, event: Any, data: dict[str, Any]) -> Any:
        callback_data = str(getattr(event, "data", "") or "")
        if callback_data not in MIX_ENTRY_CALLBACKS:
            return await handler(event, data)
        try:
            manager = getattr(app, "rd_control_mode_manager", None)
            guard = getattr(manager, "guard", None)
            if guard is None:
                raise RuntimeError("RD ownership guard unavailable")
            live = await guard._raw_live()
        except Exception:
            try:
                await event.answer(
                    "Не удалось подтвердить live Mix eligibility; действие заблокировано",
                    show_alert=True,
                )
            except Exception:
                pass
            return None
        if not potential_mix_live(live):
            try:
                await event.answer(
                    "Текущая уставка RD не является high-voltage Mix. "
                    "Используйте Pb-подхват или обычный Manual workflow.",
                    show_alert=True,
                )
            except Exception:
                pass
            return None
        return await handler(event, data)

    # Old Telegram messages can outlive the current keyboard. Gate callback entry as
    # well as presentation so a stale Mix button cannot reopen an inapplicable flow.
    observer = getattr(getattr(app, "router", None), "callback_query", None)
    middleware_manager = getattr(observer, "outer_middleware", None)
    register = getattr(middleware_manager, "register", None)
    if callable(register):
        register(entry_gate)
    elif callable(middleware_manager):
        middleware_manager(entry_gate)
    else:
        raise RuntimeError("aiogram callback outer middleware is unavailable")

    app._mix_action_eligibility_installed = True
