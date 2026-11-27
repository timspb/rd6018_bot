"""Telegram routes for canonical charge-program selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import F
from aiogram.filters import Command

from application.intents import OperatorIntent, OperatorIntentKind
from runtime.ui.actions import UIAction
from runtime.ui.components.hmi_values import StartFeedbackResult
from runtime.ui.routing.registry import route_for
from runtime.ui.screens.charge import build_charge_program_screen
from runtime.ui.telegram.renderer import (
    callback_data_for,
    decode_callback_data,
    render_screen_markup,
    render_screen_text,
)
from pb_domain import BatteryCondition, ChargeIntent
from runtime.ui.telegram import battery_selection
from ui_support import intent_label


async def handle_capacity_input(
    message: Any,
    profile: str,
    user_id: int,
    *,
    route: Any,
    pending_intent: Dict[int, ChargeIntent],
    parse_mode: Any,
    logger: Any,
    format_start_feedback: Callable[[StartFeedbackResult], str],
) -> None:
    """Validate the active wizard's capacity and submit through composed START."""
    text = (message.text or "").strip()
    try:
        ah = int(float(text))
        if ah < 1 or ah > 500:
            await message.answer("Введите число от 1 до 500.")
            return
    except ValueError:
        await message.answer("Введите число (например 60).")
        return

    if route is None:
        logger.error(
            "START denied: production start route is not composed; direct legacy START is retired"
        )
        await message.answer(
            "❌ START недоступен: production-маршрут запуска не собран. "
            "Старый прямой запуск отключён.",
            parse_mode=parse_mode,
        )
        return

    intent = OperatorIntent(
        OperatorIntentKind.START_CHARGE,
        "telegram",
        str(user_id),
        {
            "profile": profile,
            "capacity_ah": ah,
            "battery_identity": None,
            "battery_id": "operator-battery",
            "intent": pending_intent.get(user_id, ChargeIntent.NORMAL),
            "condition": BatteryCondition.UNKNOWN,
        },
    )
    result = await route.submit(intent)
    if not result.accepted:
        await message.answer(f"START отклонён: {result.reason}", parse_mode=parse_mode)
        return

    await message.answer(format_start_feedback(result), parse_mode=parse_mode)

CHARGE_CALLBACK_DATA = callback_data_for(UIAction.OPEN_CHARGE)
PROFILE_CALLBACK_PREFIX = callback_data_for(UIAction.SELECT_PROFILE)
BATTERIES_CALLBACK_DATA = callback_data_for(UIAction.OPEN_BATTERIES)
BATTERY_ADD_CALLBACK_DATA = callback_data_for(UIAction.OPEN_BATTERY_ADD)
MANUAL_CALLBACK_DATA = callback_data_for(UIAction.OPEN_MANUAL)
INTERRUPTED_MANUAL_CALLBACK_DATA = callback_data_for(UIAction.OPEN_INTERRUPTED_MANUAL)


@dataclass(frozen=True)
class PendingStart:
    """Process-local selection for the existing Telegram charge-program wizard."""

    profile: str
    capacity_ah: float
    intent: ChargeIntent
    battery_id: str
    condition: BatteryCondition
    recipe_id: str | None = None
    recipe_version: int | None = None
    native_recipe_name: str | None = None
    native_recipe_version: int | None = None


_pending_profile: Dict[int, str] = {}
_pending_intent: Dict[int, ChargeIntent] = {}
_pending_start: Dict[int, PendingStart] = {}


def selected_program_for_user(user_id: int) -> Optional[str]:
    """Project the existing process-local charge-program selection for display."""
    user_id = int(user_id)
    pending = _pending_start.get(user_id)
    if pending is not None:
        return f"{pending.profile} {pending.capacity_ah:g} Ah · {intent_label(pending.intent)}"
    profile = _pending_profile.get(user_id)
    if profile:
        return f"{profile} · ожидается ёмкость АКБ"
    record = battery_selection.selected_battery_for_user(user_id)
    if record is not None:
        return f"{record.identity.chemistry.value} {record.identity.nominal_capacity_ah:g} Ah · выбрана АКБ"
    return None


def _clear_pending_program_state(app: Any, user_id: int) -> None:
    """Clear only this user's accepted START wizard state, retaining battery choice."""
    user_id = int(user_id)
    _pending_start.pop(user_id, None)
    _pending_profile.pop(user_id, None)
    _pending_intent.pop(user_id, None)
    awaiting = getattr(app, "awaiting_ah", None)
    if isinstance(awaiting, dict):
        awaiting.pop(user_id, None)


def legacy_profile_from_callback(data: str) -> str | None:
    """Map active legacy profile callback payloads to canonical profile names."""
    return {
        "v2_profile_caca": "Ca/Ca",
        "v2_profile_efb": "EFB",
        "v2_profile_agm": "AGM",
    }.get(data)


def install_charge_program_screen(
    app: Any,
    *,
    profile_selector: Callable[[Any, str], Awaitable[None]],
    batteries_handler: Callable[[Any], Awaitable[None]],
    battery_add_handler: Callable[[Any], Awaitable[None]],
    manual_handler: Callable[[Any], Awaitable[None]],
    interrupted_manual_handler: Callable[[Any], Awaitable[None]] | None = None,
    interrupted_manual_provider: Callable[[], bool] | None = None,
    schedule_refresh: Callable[[int, int], None] | None = None,
) -> None:
    """Install canonical charge menu while preserving existing workflow owners."""

    if bool(getattr(app, "_v3_charge_program_installed", False)):
        return
    if not route_for(UIAction.OPEN_CHARGE).navigation_only:
        raise RuntimeError("charge-program screen must remain navigation-only")
    profile_route = route_for(UIAction.SELECT_PROFILE)
    if profile_route.intent_kind is not OperatorIntentKind.SELECT_CHARGE_PROFILE:
        raise RuntimeError("profile selection must route through SELECT_CHARGE_PROFILE")

    def manual_interrupted() -> bool:
        if interrupted_manual_provider is None:
            return False
        try:
            return bool(interrupted_manual_provider())
        except Exception:
            return False

    async def render(event: Any, *, schedule: bool = False) -> None:
        message = event.message if getattr(event, "message", None) is not None else event
        user = getattr(event, "from_user", None)
        user_id = int(getattr(user, "id", 0) or 0)
        chat_id = int(message.chat.id)
        app.last_chat_id = chat_id
        app.last_user_id = user_id
        screen = build_charge_program_screen(
            manual_interrupted=manual_interrupted(),
        )
        await message.answer(
            render_screen_text(screen),
            parse_mode=app.ParseMode.HTML,
            reply_markup=render_screen_markup(screen),
        )
        # OPEN_CHARGE enters the program-selection workspace. Its response,
        # not the global dashboard, must be the last Telegram message until
        # the workflow explicitly finishes. PanelLastMiddleware owns exit.

    @app.router.message(Command("modes"))
    async def _modes_command(message: Any) -> None:
        if not await app._check_chat_and_respond(message):
            return
        await render(message, schedule=True)

    @app.router.callback_query(F.data == CHARGE_CALLBACK_DATA)
    async def _charge_open(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        await render(call)

    @app.router.callback_query(F.data.startswith(PROFILE_CALLBACK_PREFIX + "?"))
    async def _profile(call: Any) -> None:
        try:
            action, payload = decode_callback_data(str(call.data or ""))
        except ValueError:
            await call.answer("Некорректный профиль", show_alert=True)
            return
        if action is not UIAction.SELECT_PROFILE:
            await call.answer("Некорректный профиль", show_alert=True)
            return
        profile = str(payload.get("profile") or "")
        await profile_selector(call, profile)

    @app.router.callback_query(F.data == BATTERIES_CALLBACK_DATA)
    async def _batteries(call: Any) -> None:
        await batteries_handler(call)

    @app.router.callback_query(F.data == BATTERY_ADD_CALLBACK_DATA)
    async def _battery_add(call: Any) -> None:
        await battery_add_handler(call)

    @app.router.callback_query(F.data == MANUAL_CALLBACK_DATA)
    async def _manual(call: Any) -> None:
        await manual_handler(call)

    @app.router.callback_query(F.data == INTERRUPTED_MANUAL_CALLBACK_DATA)
    async def _manual_interrupted(call: Any) -> None:
        if interrupted_manual_handler is None or not manual_interrupted():
            await call.answer("Прерванной Manual-сессии больше нет", show_alert=True)
            return
        await interrupted_manual_handler(call)

    app._v3_modes_command_handler = _modes_command
    app._v3_charge_program_handler = _charge_open
    app._v3_charge_profile_handler = _profile
    app._v3_charge_program_installed = True


__all__ = [
    "BATTERIES_CALLBACK_DATA",
    "BATTERY_ADD_CALLBACK_DATA",
    "CHARGE_CALLBACK_DATA",
    "INTERRUPTED_MANUAL_CALLBACK_DATA",
    "MANUAL_CALLBACK_DATA",
    "PROFILE_CALLBACK_PREFIX",
    "install_charge_program_screen",
    "handle_capacity_input",
]
