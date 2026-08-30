from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Any, Dict, Optional

from aiogram import F
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from battery_registry import BatteryRecord, upsert_battery
from pb_domain import (
    BatteryChemistry,
    BatteryCondition,
    BatteryIdentity,
    BatteryLifecycle,
    ChargeIntent,
)
from v2_battery_catalog import list_batteries
from v2_ui import (
    battery_button_label,
    build_program_preview,
    format_active_evidence,
    format_battery_card,
    intent_label,
    profile_for_chemistry,
)


@dataclass(frozen=True)
class PendingStart:
    profile: str
    capacity_ah: float
    intent: ChargeIntent
    battery_id: str
    condition: BatteryCondition


_pending_profile: Dict[int, str] = {}
_pending_intent: Dict[int, ChargeIntent] = {}
_pending_start: Dict[int, PendingStart] = {}
_battery_pages: Dict[int, list[BatteryRecord]] = {}
_selected_battery: Dict[int, BatteryRecord] = {}
_new_battery_input: set[int] = set()
_installed = False


def _intent_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⚡ Обычный", callback_data=f"{prefix}_normal"),
                InlineKeyboardButton(text="🛠 Recovery", callback_data=f"{prefix}_recovery"),
            ],
            [
                InlineKeyboardButton(text="🔄 Condition", callback_data=f"{prefix}_conditioning"),
                InlineKeyboardButton(text="🔬 Диагностика", callback_data=f"{prefix}_diagnostic"),
            ],
            [InlineKeyboardButton(text="⬅️ Режимы", callback_data="charge_modes")],
        ]
    )


def _preview_keyboard(start_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Запустить", callback_data=start_callback)],
            [InlineKeyboardButton(text="⬅️ Режимы", callback_data="charge_modes")],
        ]
    )


def _parse_intent(value: str) -> ChargeIntent:
    return ChargeIntent(str(value).strip().lower())


def _parse_chemistry(value: str) -> BatteryChemistry:
    raw = str(value).strip().lower().replace(" ", "").replace("-", "_")
    aliases = {
        "agm": BatteryChemistry.AGM,
        "efb": BatteryChemistry.EFB,
        "ca": BatteryChemistry.CA_CA,
        "caca": BatteryChemistry.CA_CA,
        "ca/ca": BatteryChemistry.CA_CA,
        "ca_ca": BatteryChemistry.CA_CA,
        "flooded": BatteryChemistry.FLOODED,
        "liquid": BatteryChemistry.FLOODED,
    }
    try:
        return aliases[raw]
    except KeyError as exc:
        raise ValueError("тип должен быть AGM, EFB, Ca/Ca или Flooded") from exc


def parse_battery_spec(text: str) -> tuple[BatteryIdentity, BatteryLifecycle]:
    """Parse one-line registry input: ID | chemistry | Ah | manufacturer | model."""
    parts = [part.strip() for part in str(text or "").split("|")]
    if len(parts) < 3:
        raise ValueError("формат: ID | AGM/EFB/Ca/Ca | Ah | производитель | модель")
    battery_id = parts[0]
    if not battery_id or len(battery_id) > 64:
        raise ValueError("ID обязателен и должен быть короче 65 символов")
    chemistry = _parse_chemistry(parts[1])
    try:
        capacity = float(parts[2].replace(",", "."))
    except ValueError as exc:
        raise ValueError("ёмкость Ah должна быть числом") from exc
    if capacity <= 0 or capacity > 1000:
        raise ValueError("ёмкость должна быть в диапазоне 0..1000 Ah")
    manufacturer = parts[3] if len(parts) >= 4 else ""
    model = parts[4] if len(parts) >= 5 else ""
    identity = BatteryIdentity(
        battery_id=battery_id,
        chemistry=chemistry,
        nominal_capacity_ah=capacity,
        manufacturer=manufacturer,
        model=model,
    )
    return identity, BatteryLifecycle(condition=BatteryCondition.UNKNOWN)


def _profile_from_callback(data: str) -> Optional[str]:
    return {
        "v2_profile_caca": "Ca/Ca",
        "v2_profile_efb": "EFB",
        "v2_profile_agm": "AGM",
    }.get(data)


async def _safe_answer(event: Any, text: str, *, reply_markup=None) -> None:
    message = event.message if hasattr(event, "message") and event.message is not None else event
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)


async def _start_profile(app: Any, event: Any, pending: PendingStart) -> bool:
    message = event.message if hasattr(event, "message") and event.message is not None else event
    user = getattr(event, "from_user", None) or getattr(message, "from_user", None)
    user_id = user.id if user else 0

    if app.charge_controller.is_active:
        await message.answer("⚠️ Сначала остановите текущую сессию.")
        return False

    live = await app.hass.get_all_live()
    battery_v = app._safe_float(live.get("battery_voltage"))
    current = app._safe_float(live.get("current"))
    temp_ext_raw = live.get("temp_ext")
    if temp_ext_raw in (None, "", "unknown", "unavailable"):
        await message.answer("❌ Нет валидной температуры temp_ext. V2 не разрешает запуск без датчика АКБ.")
        return False
    temp_ext = app._safe_float(temp_ext_raw)
    ah_now = app._safe_float(live.get("ah"))
    input_v = app._safe_float(live.get("input_voltage"), 0.0)
    ovp_triggered = str(live.get("ovp_triggered", "")).lower() == "on"
    ocp_triggered = str(live.get("ocp_triggered", "")).lower() == "on"

    if temp_ext < app.MIN_START_TEMP:
        await message.answer(
            f"❌ temp_ext {temp_ext:.1f}°C ниже стартового порога {app.MIN_START_TEMP:.0f}°C."
        )
        return False
    if ovp_triggered or ocp_triggered:
        await message.answer("❌ На RD6018 активен флаг OVP/OCP. Сначала проверьте и сбросьте защиту.")
        return False
    if input_v > 0 and input_v < app.MIN_INPUT_VOLTAGE:
        await message.answer(
            f"❌ Вход БП {input_v:.0f}V ниже {app.MIN_INPUT_VOLTAGE:.0f}V."
        )
        return False

    app.charge_controller.configure_recovery_context(
        battery_id=pending.battery_id,
        intent=pending.intent,
        condition_before=pending.condition,
    )
    app.charge_controller.start(pending.profile, int(round(pending.capacity_ah)))
    if battery_v < 12.0:
        uv, ui = app.charge_controller._prep_target(temp_ext)
    else:
        uv, ui = app.charge_controller._main_target(temp_ext)

    # Same transaction ordering as the production bot: protections -> setpoints -> ON.
    await app._apply_phase_protection(uv, ui)
    await app.hass.set_voltage(uv)
    await app.hass.set_current(app._cap_current(ui))
    await app.hass.turn_on(app.ENTITY_MAP["switch"])

    app.last_checkpoint_time = app.time.time()
    app.last_chat_id = message.chat.id
    app.last_user_id = user_id
    app.log_event(
        app.charge_controller.current_stage,
        battery_v,
        current,
        temp_ext,
        ah_now,
        f"V2_START | intent={pending.intent.value} battery={pending.battery_id}",
    )
    await message.answer(
        f"✅ <b>V2 заряд запущен</b>\n"
        f"{html.escape(pending.profile)} {pending.capacity_ah:g}Ah · {html.escape(intent_label(pending.intent))}\n"
        f"АКБ: <code>{html.escape(pending.battery_id)}</code>",
        parse_mode=ParseMode.HTML,
    )
    try:
        old = app.user_dashboard.get(user_id)
        await app.send_dashboard(message, old_msg_id=old)
    except Exception:
        pass
    return True


def install_v2_ui(app: Any) -> None:
    """Install the V2 Telegram presentation/workflow over the legacy monolithic bot.

    The legacy module remains an emergency rollback entrypoint.  This installer only
    replaces presentation functions and adds callback handlers; HA polling, watchdogs,
    logging and the existing manual/custom workflow stay untouched.
    """
    global _installed
    if _installed:
        return
    _installed = True

    original_dashboard_keyboard = app._build_dashboard_keyboard
    original_progress = app._format_stage_progress_line
    original_handle_ah = app.handle_ah_input
    original_handle_dialog = app.handle_dialog_mode

    def build_dashboard_keyboard(is_on: bool, user_id: int, *, back_to_dashboard: bool = False):
        markup = original_dashboard_keyboard(is_on, user_id, back_to_dashboard=back_to_dashboard)
        rows = list(markup.inline_keyboard)
        insert_at = max(0, len(rows) - (2 if back_to_dashboard else 1))
        rows.insert(
            insert_at,
            [
                InlineKeyboardButton(text="🔋 АКБ", callback_data="v2_batteries"),
                InlineKeyboardButton(text="🧭 V2", callback_data="v2_status"),
            ],
        )
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def charge_modes_text() -> str:
        return (
            "<b>🧭 V2 · программа заряда</b>\n\n"
            "Сначала выберите химию или сохранённую физическую батарею, затем <b>intent</b>.\n\n"
            "⚡ Normal — полный штатный AUTO; Recovery/Mix включаются только по критериям V2.\n"
            "🛠 Recovery — восстановительный intent с HV только в разрешённом recipe/diagnostic envelope.\n"
            "🔄 Conditioning — сервисный режим в recipe envelope.\n"
            "🔬 Diagnostic — без автоматической HV-эскалации.\n\n"
            "В CV финиш оценивается по <b>Imin→ΔI</b>, в CC — по <b>Vmax→ΔV</b>."
        )

    def build_charge_modes_keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🟦 Ca/Ca", callback_data="v2_profile_caca"),
                    InlineKeyboardButton(text="🟧 EFB", callback_data="v2_profile_efb"),
                    InlineKeyboardButton(text="🟥 AGM", callback_data="v2_profile_agm"),
                ],
                [
                    InlineKeyboardButton(text="🔋 Мои АКБ", callback_data="v2_batteries"),
                    InlineKeyboardButton(text="➕ АКБ", callback_data="v2_battery_add"),
                ],
                [
                    InlineKeyboardButton(text="🛠 Custom", callback_data="profile_custom"),
                    InlineKeyboardButton(text="⏹ Off", callback_data="menu_off"),
                ],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="charge_back")],
            ]
        )

    def format_stage_progress_line(live: Dict[str, Any]) -> str:
        if app.charge_controller.is_active and app.charge_controller.current_stage in {
            app.charge_controller.STAGE_MAIN,
            app.charge_controller.STAGE_MIX,
        }:
            try:
                snap = app.charge_controller.v2_ui_snapshot()
                compact = format_active_evidence(
                    snap,
                    voltage_v=app._safe_float(live.get("battery_voltage")),
                    current_a=app._safe_float(live.get("current")),
                    temp_c=app._safe_float(live.get("temp_ext")),
                )
                return compact
            except Exception:
                pass
        return original_progress(live)

    async def handle_ah_input(message: Any, profile: str, user_id: int) -> None:
        intent = _pending_intent.pop(user_id, ChargeIntent.RECOVERY)
        try:
            capacity = float((message.text or "").strip().replace(",", "."))
        except ValueError:
            await original_handle_ah(message, profile, user_id)
            return
        if capacity < 1 or capacity > 500:
            await original_handle_ah(message, profile, user_id)
            return
        app.awaiting_ah.pop(user_id, None)
        pending = PendingStart(
            profile=profile,
            capacity_ah=capacity,
            intent=intent,
            battery_id=f"adhoc:{profile}:{capacity:g}:{user_id}",
            condition=BatteryCondition.UNKNOWN,
        )
        _pending_start[user_id] = pending
        preview = build_program_preview(
            profile=profile,
            capacity_ah=capacity,
            intent=intent,
            condition=BatteryCondition.UNKNOWN,
            battery_id=pending.battery_id,
        )
        await message.answer(
            preview.text,
            parse_mode=ParseMode.HTML,
            reply_markup=_preview_keyboard("v2_quick_start"),
        )

    async def handle_dialog_mode(message: Any) -> None:
        user_id = message.from_user.id if message.from_user else 0
        if user_id not in _new_battery_input:
            await original_handle_dialog(message)
            return
        try:
            identity, lifecycle = parse_battery_spec(message.text or "")
            await upsert_battery(identity, lifecycle)
        except Exception as exc:
            await message.answer(
                f"❌ {html.escape(str(exc))}\n\n"
                "Формат: <code>ID | AGM/EFB/Ca/Ca | Ah | Производитель | Модель</code>",
                parse_mode=ParseMode.HTML,
            )
            return
        _new_battery_input.discard(user_id)
        records = await list_batteries(limit=50)
        created = next((item for item in records if item.identity.battery_id == identity.battery_id), None)
        text = format_battery_card(created) if created else f"✅ АКБ <code>{html.escape(identity.battery_id)}</code> сохранена."
        await message.answer(text, parse_mode=ParseMode.HTML)

    app._build_dashboard_keyboard = build_dashboard_keyboard
    app._charge_modes_text = charge_modes_text
    app._build_charge_modes_keyboard = build_charge_modes_keyboard
    app._format_stage_progress_line = format_stage_progress_line
    app.handle_ah_input = handle_ah_input
    app.handle_dialog_mode = handle_dialog_mode

    @app.router.callback_query(F.data == "v2_status")
    async def v2_status_handler(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        live = await app.hass.get_all_live()
        snap = app.charge_controller.v2_ui_snapshot()
        text = format_active_evidence(
            snap,
            voltage_v=app._safe_float(live.get("battery_voltage")),
            current_a=app._safe_float(live.get("current")),
            temp_c=app._safe_float(live.get("temp_ext")),
        )
        await _safe_answer(
            call,
            f"<b>🧭 V2 controller</b>\n\n{text}\n\n"
            f"Stage: <code>{html.escape(app.charge_controller.current_stage)}</code>",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ Дашборд", callback_data="dash_back")]]
            ),
        )

    @app.router.callback_query(F.data == "v2_batteries")
    async def batteries_handler(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        user_id = call.from_user.id if call.from_user else 0
        records = [r for r in await list_batteries(limit=20) if profile_for_chemistry(r.identity.chemistry)]
        _battery_pages[user_id] = records
        if not records:
            await _safe_answer(
                call,
                "<b>🔋 Реестр АКБ пуст.</b>\nДобавьте физическую батарею или используйте быстрый профиль.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="➕ Добавить АКБ", callback_data="v2_battery_add")],
                        [InlineKeyboardButton(text="⬅️ Режимы", callback_data="charge_modes")],
                    ]
                ),
            )
            return
        rows = [
            [InlineKeyboardButton(text=battery_button_label(record), callback_data=f"v2_battery_{idx}")]
            for idx, record in enumerate(records)
        ]
        rows.append([InlineKeyboardButton(text="➕ Добавить АКБ", callback_data="v2_battery_add")])
        rows.append([InlineKeyboardButton(text="⬅️ Режимы", callback_data="charge_modes")])
        await _safe_answer(
            call,
            "<b>🔋 Физические аккумуляторы</b>\nВыберите батарею:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )

    @app.router.callback_query(F.data == "v2_battery_add")
    async def battery_add_handler(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        user_id = call.from_user.id if call.from_user else 0
        _new_battery_input.add(user_id)
        await _safe_answer(
            call,
            "<b>➕ Добавление АКБ</b>\n\n"
            "Одним сообщением:\n"
            "<code>ID | AGM/EFB/Ca/Ca | Ah | Производитель | Модель</code>\n\n"
            "Например:\n<code>varta70 | AGM | 70 | Varta | Silver Dynamic AGM</code>",
        )

    @app.router.callback_query(F.data.startswith("v2_battery_") & ~F.data.in_({"v2_battery_add"}))
    async def battery_select_handler(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        user_id = call.from_user.id if call.from_user else 0
        raw = (call.data or "").replace("v2_battery_", "", 1)
        if not raw.isdigit():
            return
        idx = int(raw)
        records = _battery_pages.get(user_id) or []
        if idx < 0 or idx >= len(records):
            await call.answer("Список устарел, откройте АКБ заново", show_alert=True)
            return
        record = records[idx]
        _selected_battery[user_id] = record
        await _safe_answer(
            call,
            f"{format_battery_card(record)}\n\n<b>Что делаем?</b>",
            reply_markup=_intent_keyboard("v2_bat_intent"),
        )

    @app.router.callback_query(F.data.startswith("v2_profile_"))
    async def quick_profile_handler(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        profile = _profile_from_callback(call.data or "")
        if not profile:
            return
        user_id = call.from_user.id if call.from_user else 0
        _pending_profile[user_id] = profile
        await _safe_answer(
            call,
            f"<b>{html.escape(profile)}</b>\nВыберите intent. Normal — полный штатный AUTO; стандартный Recovery/Mix используется только по критериям V2.",
            reply_markup=_intent_keyboard("v2_quick_intent"),
        )

    @app.router.callback_query(F.data.startswith("v2_quick_intent_"))
    async def quick_intent_handler(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        user_id = call.from_user.id if call.from_user else 0
        profile = _pending_profile.get(user_id)
        if not profile:
            await call.answer("Сначала выберите профиль", show_alert=True)
            return
        intent = _parse_intent((call.data or "").replace("v2_quick_intent_", "", 1))
        _pending_intent[user_id] = intent
        app.awaiting_ah[user_id] = profile
        await _safe_answer(
            call,
            f"{html.escape(intent_label(intent))} · <b>{html.escape(profile)}</b>\n\nВведите ёмкость АКБ в Ah. После ввода покажу программу перед запуском.",
        )

    @app.router.callback_query(F.data == "v2_quick_start")
    async def quick_start_handler(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        user_id = call.from_user.id if call.from_user else 0
        pending = _pending_start.get(user_id)
        if pending is None:
            await call.answer("Preview устарел — выберите режим заново", show_alert=True)
            return
        if await _start_profile(app, call, pending):
            _pending_start.pop(user_id, None)

    @app.router.callback_query(F.data.startswith("v2_bat_intent_"))
    async def battery_intent_handler(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        user_id = call.from_user.id if call.from_user else 0
        record = _selected_battery.get(user_id)
        if record is None:
            await call.answer("Сначала выберите АКБ", show_alert=True)
            return
        profile = profile_for_chemistry(record.identity.chemistry)
        if profile is None:
            await call.answer("Для этой химии пока нет auto-profile", show_alert=True)
            return
        intent = _parse_intent((call.data or "").replace("v2_bat_intent_", "", 1))
        pending = PendingStart(
            profile=profile,
            capacity_ah=record.identity.nominal_capacity_ah,
            intent=intent,
            battery_id=record.identity.battery_id,
            condition=record.lifecycle.condition,
        )
        _pending_start[user_id] = pending
        preview = build_program_preview(
            profile=profile,
            capacity_ah=pending.capacity_ah,
            intent=intent,
            condition=pending.condition,
            battery_id=pending.battery_id,
        )
        await _safe_answer(
            call,
            f"{format_battery_card(record)}\n\n{preview.text}",
            reply_markup=_preview_keyboard("v2_battery_start"),
        )

    @app.router.callback_query(F.data == "v2_battery_start")
    async def battery_start_handler(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        user_id = call.from_user.id if call.from_user else 0
        pending = _pending_start.get(user_id)
        if pending is None:
            await call.answer("Preview устарел — выберите АКБ заново", show_alert=True)
            return
        if await _start_profile(app, call, pending):
            _pending_start.pop(user_id, None)