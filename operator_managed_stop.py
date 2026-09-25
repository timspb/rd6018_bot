from __future__ import annotations

import html
from typing import Any

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import operator_hmi as hmi
import telegram_panel
from operator_confirmation import ConfirmationStore
from rd_hands_off_release import _active_session_token, _auto_active, _manual_active
from application.intents import OperatorIntent, OperatorIntentKind
from runtime_safety import OutputOffNotConfirmed


STOP_CONFIRM_CALLBACK = "operator_managed_stop"
STOP_EXECUTE_CALLBACK = "operator_managed_stop_execute"
STOP_CANCEL_CALLBACK = "operator_managed_stop_cancel"


async def _route_stop_intent(app: Any, call: Any) -> bool:
    """Pass STOP through the application boundary before old confirmation logic."""
    interface = getattr(app, "operator_interface", None)
    submit = getattr(interface, "submit_intent", None)
    if not callable(submit):
        return True
    user = str(getattr(getattr(call, "from_user", None), "id", "0"))
    result = await submit(OperatorIntent(OperatorIntentKind.STOP_CHARGE, "telegram", user))
    if getattr(result, "status", None) == "rejected":
        await call.answer("Остановка пока недоступна", show_alert=True)
        return False
    return True


def _replace_legacy_power_toggle(
    markup: InlineKeyboardMarkup,
    state: hmi.OperatorHmiState,
) -> InlineKeyboardMarkup:
    """Give the semantic HMI a stop-only callback, never a legacy ON/OFF toggle."""
    if state.authority not in {hmi.HmiAuthority.AUTO, hmi.HmiAuthority.MANUAL}:
        return markup
    rows = []
    for row in markup.inline_keyboard:
        replaced = []
        for button in row:
            if str(getattr(button, "callback_data", "") or "") == "power_toggle":
                replaced.append(
                    InlineKeyboardButton(
                        text=str(getattr(button, "text", "") or "🛑 Остановить заряд"),
                        callback_data=STOP_CONFIRM_CALLBACK,
                    )
                )
            else:
                replaced.append(button)
        rows.append(replaced)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _session_label(token: str) -> str:
    if token.startswith("manual"):
        return "Manual"
    if token.startswith("auto"):
        return "AUTO"
    return "managed"


async def _stop_exact_session(app: Any, expected_token: str) -> tuple[bool, str]:
    """Stop only the session for which the operator confirmed destructive action.

    The confirmation callback is deliberately not a power toggle. If the managed
    owner changes before execution, no actuator command is issued. Manual is retired
    by its own runtime manager; AUTO uses the existing verified hard-stop path.
    """
    current = _active_session_token(app)
    if current is None:
        return False, "Управляемая сессия уже не активна или ownership неоднозначен."
    if current != expected_token:
        return False, "Подтверждение устарело: активная сессия изменилась. Команда не выполнена."

    if expected_token.startswith("manual"):
        manager = getattr(app, "manual_session_manager", None)
        if manager is None or not _manual_active(app):
            return False, "Manual-сессия уже изменилась. Команда не выполнена."
        try:
            confirmed = bool(await manager.stop("operator_stop"))
        except Exception as exc:
            return False, f"Output OFF для Manual не подтверждён: {type(exc).__name__}: {exc}"
        if not confirmed:
            return False, "Output OFF для Manual не подтверждён; runtime остаётся в containment."
        retire = getattr(manager, "_retire_runner", None)
        if callable(retire):
            await retire()
        clear = getattr(app, "_clear_manual_off", None)
        if callable(clear):
            clear()
        return True, "Manual остановлен; Output OFF подтверждён."

    if expected_token.startswith("auto"):
        if not _auto_active(app):
            return False, "AUTO-сессия уже изменилась. Команда не выполнена."
        hard_stop = getattr(app, "_hard_stop_charge", None)
        if not callable(hard_stop):
            return False, "AUTO stop недоступен: verified hard-stop path не установлен."
        try:
            await hard_stop()
        except OutputOffNotConfirmed as exc:
            if await _retire_auto_after_unconfirmed_off(app):
                return False, (
                    "Output OFF не подтверждён edge-readback; ток 0 A и readback OFF, "
                    "software AUTO-сессия сброшена в containment: "
                    f"{type(exc).__name__}: {exc}"
                )
            return False, f"AUTO stop не завершён: {type(exc).__name__}: {exc}"
        except Exception as exc:
            return False, f"AUTO stop не завершён: {type(exc).__name__}: {exc}"
        if _auto_active(app):
            return False, "Output stop вернулся без ошибки, но AUTO authority остался активен."
        clear = getattr(app, "_clear_manual_off", None)
        if callable(clear):
            clear()
        return True, "AUTO остановлен; Output OFF подтверждён."

    return False, "Неизвестный managed owner; команда не выполнена."


async def _retire_auto_after_unconfirmed_off(app: Any) -> bool:
    """Retire software AUTO only when a read-only OFF/zero-current snapshot agrees."""
    hass = getattr(app, "hass", None)
    get_live = getattr(hass, "get_all_live", None)
    if not callable(get_live):
        return False
    try:
        live = await get_live()
    except Exception:
        return False

    raw_code = live.get("output_state_code_v2")
    try:
        output_code = float(raw_code) if raw_code not in (None, "") else None
    except (TypeError, ValueError):
        output_code = None
    if output_code is not None:
        output_off = output_code == 0.0
    else:
        output_off = str(live.get("switch", "")).strip().lower() in {"off", "false", "0"}
    try:
        current = float(live.get("current"))
    except (TypeError, ValueError):
        current = None
    if not output_off or current is None or current > 0.05:
        return False

    controller = getattr(app, "charge_controller", None)
    stop = getattr(controller, "stop", None)
    if not callable(stop):
        return False
    stop(clear_session=True)
    clear = getattr(app, "_clear_manual_off", None)
    if callable(clear):
        clear()
    return True


def install_operator_managed_stop(app: Any) -> None:
    """Replace the legacy dual-purpose power toggle with exact-session L4 Stop."""
    if bool(getattr(app, "_operator_managed_stop_installed", False)):
        return

    confirmations = ConfirmationStore()
    app._operator_managed_stop_confirmations = confirmations

    base_keyboard = hmi.build_operator_keyboard

    def stop_only_keyboard(
        app_arg: Any,
        state: hmi.OperatorHmiState,
        *,
        actions: Any = None,
    ) -> InlineKeyboardMarkup:
        base = (
            base_keyboard(app_arg, state, actions=actions)
            if actions is not None
            else base_keyboard(app_arg, state)
        )
        if actions is not None:
            return base
        return _replace_legacy_power_toggle(base, state)

    hmi.build_operator_keyboard = stop_only_keyboard

    # The terminal-panel middleware is already installed before the final HMI. Teach
    # it that Stop confirmation is an L4 workspace and execute/cancel are terminal.
    telegram_panel._WORKSPACE_CALLBACKS.add(STOP_CONFIRM_CALLBACK)
    telegram_panel._TERMINAL_CALLBACKS.update(
        {STOP_EXECUTE_CALLBACK, STOP_CANCEL_CALLBACK}
    )

    async def _restore_text_panel_after_failed_stop(call: Any) -> None:
        """Leave the graph workspace after an unconfirmed stop without lying."""
        user_id = call.from_user.id if call.from_user else 0
        chat_id = call.message.chat.id
        retire = getattr(app, "_retire_graph_workspace_for_user", None)
        if callable(retire):
            await retire(chat_id, user_id)
        manager = getattr(app, "terminal_panel_manager", None)
        restore = getattr(manager, "ensure_text_last", None)
        if callable(restore):
            await restore(chat_id, user_id)

    @app.router.callback_query(F.data == STOP_CONFIRM_CALLBACK)
    async def _managed_stop_confirm(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        if not await _route_stop_intent(app, call):
            return
        token = _active_session_token(app)
        if token is None:
            await call.answer(
                "Нет однозначной активной managed-сессии",
                show_alert=True,
            )
            return
        if not confirmations.issue_for_call(call, token):
            await call.answer(
                "Не удалось привязать подтверждение к текущему чату",
                show_alert=True,
            )
            return
        await call.answer()
        label = _session_label(token)
        await call.message.answer(
            "<b>Остановить заряд?</b>\n\n"
            f"Будет остановлена только текущая сессия <b>{html.escape(label)}</b>. "
            "Команда выполняет verified Output OFF и не может включить выход. "
            "Подтверждение действительно ограниченное время и только в этом чате.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🛑 ОСТАНОВИТЬ",
                            callback_data=STOP_EXECUTE_CALLBACK,
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="Продолжить заряд",
                            callback_data=STOP_CANCEL_CALLBACK,
                        )
                    ],
                ]
            ),
        )

    @app.router.callback_query(F.data == STOP_CANCEL_CALLBACK)
    async def _managed_stop_cancel(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        confirmations.cancel_for_call(call)
        await call.answer("Заряд продолжается")

    @app.router.callback_query(F.data == STOP_EXECUTE_CALLBACK)
    async def _managed_stop_execute(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        expected = confirmations.consume_for_call(call)
        if not expected:
            await call.answer(
                "Подтверждение отсутствует, истекло или уже использовано",
                show_alert=True,
            )
            return

        current = _active_session_token(app)
        if current != expected:
            await call.answer(
                "Сессия изменилась — остановка отменена",
                show_alert=True,
            )
            return

        await call.answer()
        ok, detail = await _stop_exact_session(app, expected)
        if ok:
            await call.message.answer(
                f"<b>🛑 Заряд остановлен.</b> {html.escape(detail)}",
                parse_mode=app.ParseMode.HTML,
            )
        else:
            await call.message.answer(
                f"⚠️ <b>Остановка не подтверждена.</b> {html.escape(detail)}",
                parse_mode=app.ParseMode.HTML,
            )
            await _restore_text_panel_after_failed_stop(call)

    app._operator_managed_stop_installed = True
