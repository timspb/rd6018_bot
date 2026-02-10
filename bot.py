"""
bot.py — RD6018 Ultimate Telegram Controller (Async Edition).
Дашборд: один автообновляемый message с графиком, метриками и кнопками.
"""
import asyncio
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Union

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.filters import Command

from ai_engine import ask_deepseek
from charge_logic import (
    ChargeController,
    HIGH_V_FAST_TIMEOUT,
    HIGH_V_THRESHOLD,
    WATCHDOG_TIMEOUT,
)
from charging_log import log_checkpoint, log_event, rotate_if_needed
from config import ENTITY_MAP, HA_URL, HA_TOKEN, TG_TOKEN
from database import add_record, get_graph_data, get_logs_data, get_raw_history, init_db
from graphing import generate_chart
from hass_api import HassClient

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("rd6018")

if not TG_TOKEN:
    raise ValueError(
        "TG_TOKEN не задан. Укажите TG_TOKEN или TELEGRAM_BOT_TOKEN в .env"
    )

bot = Bot(token=TG_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()

hass = HassClient(HA_URL, HA_TOKEN)


def _charge_notify(msg: str) -> None:
    """Отправка уведомления от ChargeController в Telegram."""
    global last_chat_id
    if last_chat_id and msg:
        asyncio.create_task(_send_notify_safe(msg))


async def _send_notify_safe(msg: str) -> None:
    try:
        await bot.send_message(last_chat_id, msg, parse_mode=ParseMode.HTML)
    except Exception as ex:
        logger.error("charge notify failed: %s", ex)


charge_controller = ChargeController(hass, notify_cb=_charge_notify)

# Храним message_id дашборда для каждого user_id
user_dashboard: Dict[int, int] = {}
last_chat_id: Optional[int] = None
last_charge_alert_at: Optional[datetime] = None
last_idle_alert_at: Optional[datetime] = None
zero_current_since: Optional[datetime] = None
CHARGE_ALERT_COOLDOWN = timedelta(hours=1)
IDLE_ALERT_COOLDOWN = timedelta(hours=1)
ZERO_CURRENT_THRESHOLD_MINUTES = 30
awaiting_ah: Dict[int, str] = {}  # user_id -> profile (Ca/Ca, EFB, AGM)
last_ha_ok_time: float = 0.0  # для Soft Watchdog: время последнего успешного ответа HA
SOFT_WATCHDOG_TIMEOUT = 3 * 60  # сек — нет связи с HA 3 мин → Output OFF
last_checkpoint_time: float = 0.0  # для контрольных точек в лог каждые 10 мин


def _build_trend_summary(
    times: list,
    voltages: list,
    currents: list,
) -> str:
    """Сформировать краткую таблицу трендов для AI (напр. «10 мин назад: 13.2В | сейчас: 14.4В»)."""
    if not times or not voltages or not currents:
        return ""
    now = datetime.now()
    n = min(len(times), len(voltages), len(currents))
    indices = [0, max(1, n // 3), max(2, 2 * n // 3), n - 1] if n >= 4 else list(range(n))
    lines = []
    for i in indices:
        ts = times[i]
        v = voltages[i] if i < len(voltages) else 0.0
        c = currents[i] if i < len(currents) else 0.0
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00")[:19])
            delta_min = int((now - dt).total_seconds() / 60)
            label = "сейчас" if delta_min < 1 else f"{delta_min} мин назад"
        except Exception:
            label = str(ts)[-8:] if len(str(ts)) >= 8 else "?"
        lines.append(f"{label}: {v:.2f}В, {c:.2f}А")
    return " | ".join(lines)


def _md_to_html(text: str) -> str:
    """Конвертировать **жирный** в <b>жирный</b> для Telegram HTML."""
    if not text:
        return text
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def _format_time(ts: str) -> str:
    """Преобразовать ISO timestamp в HH:MM:SS."""
    if not ts:
        return "?:?:?"
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00")[:19])
        return dt.strftime("%H:%M:%S")
    except Exception:
        return str(ts)[-8:] if len(str(ts)) >= 8 else "?:?:?"


def _safe_float(val, default: float = 0.0) -> float:
    if val is None or val in ("unknown", "unavailable", ""):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


async def send_dashboard(message_or_call: Union[Message, CallbackQuery], old_msg_id: Optional[int] = None) -> int:
    """
    Сформировать и отправить дашборд.
    Anti-spam: при refresh удаляем старый message перед отправкой нового.
    """
    msg = message_or_call.message if isinstance(message_or_call, CallbackQuery) else message_or_call
    chat_id = msg.chat.id
    user_id = message_or_call.from_user.id if getattr(message_or_call, "from_user", None) else 0

    live = await hass.get_all_live()
    battery_v = _safe_float(live.get("battery_voltage"))
    output_v = _safe_float(live.get("voltage"))
    v = battery_v if not (is_on := str(live.get("switch", "")).lower() == "on") else output_v
    i = _safe_float(live.get("current"))
    p = _safe_float(live.get("power"))
    ah = _safe_float(live.get("ah"))
    wh = _safe_float(live.get("wh"))
    temp_int = _safe_float(live.get("temp_int"))
    temp_ext = _safe_float(live.get("temp_ext"))
    set_v = _safe_float(live.get("set_voltage"))
    set_i = _safe_float(live.get("set_current"))
    is_cv = str(live.get("is_cv", "")).lower() == "on"
    is_cc = str(live.get("is_cc", "")).lower() == "on"
    mode = "CV" if is_cv else ("CC" if is_cc else "-")

    status = "💤 Ожидание | АКБ: {:.2f}В".format(battery_v) if not is_on else "⚡️ Зарядка | Выход: {:.2f}В (АКБ: {:.2f}В)".format(output_v, battery_v)
    charge_phase = ""
    if charge_controller.is_active:
        charge_phase = f"\n<b>🔋 ЗАРЯД:</b> {charge_controller.current_stage} ({charge_controller.battery_type} {charge_controller.ah_capacity}Ач)"
    text = (
        "<b>📊 СТАТУС:</b> {} | {}{}\n"
        "<b>⚡ LIVE:</b> {:.2f}В | {:.2f}А | {:.2f}Вт\n"
        "<b>🎯 ЦЕЛЬ:</b> {:.2f}В | {:.1f}А\n"
        "<b>🔋 ЕМКОСТЬ:</b> {:.2f} Ач | {:.1f} Втч\n"
        "<b>🌡 ТЕМП:</b> {:.1f}°C (Внеш) | {:.1f}°C (Внутр)"
    ).format(status, mode, charge_phase, v, i, p, set_v, set_i, ah, wh, temp_ext, temp_int)

    times, voltages, currents = await get_graph_data(limit=100)
    buf = generate_chart(times, voltages, currents)
    photo = BufferedInputFile(buf.getvalue(), filename="chart.png") if buf else None

    kb_rows = [
        [InlineKeyboardButton(text="⚙️ Режимы заряда", callback_data="charge_modes")],
        [
            InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh"),
            InlineKeyboardButton(text="📈 Логи", callback_data="logs"),
            InlineKeyboardButton(text="🧠 AI Анализ", callback_data="ai_analysis"),
        ],
        [
            InlineKeyboardButton(
                text="🛑 ВЫКЛ" if is_on else "⚡ ВКЛ",
                callback_data="power_toggle",
            ),
        ],
    ]
    if charge_controller.is_active:
        kb_rows.insert(1, [InlineKeyboardButton(text="🛑 ОСТАНОВИТЬ ЗАРЯД", callback_data="charge_stop")])
    ikb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    if old_msg_id:
        try:
            await bot.delete_message(chat_id, old_msg_id)
        except Exception:
            pass
    try:
        await msg.delete()
    except Exception:
        pass

    if photo:
        sent = await bot.send_photo(chat_id, photo=photo, caption=text, reply_markup=ikb)
    else:
        sent = await bot.send_message(chat_id, text, reply_markup=ikb)

    user_dashboard[user_id] = sent.message_id
    return sent.message_id


async def soft_watchdog_loop() -> None:
    """Мягкий Watchdog: при потере связи с HA более 3 мин — Output OFF."""
    global last_ha_ok_time
    while True:
        await asyncio.sleep(10)
        try:
            if last_ha_ok_time <= 0:
                continue
            if time.time() - last_ha_ok_time >= SOFT_WATCHDOG_TIMEOUT:
                logger.critical("CRITICAL: Soft Watchdog timeout (HA connection lost 3min). Emergency Output OFF.")
                try:
                    live = await hass.get_all_live()
                    v = _safe_float(live.get("battery_voltage"))
                    i = _safe_float(live.get("current"))
                    t = _safe_float(live.get("temp_ext"))
                    ah = _safe_float(live.get("ah"))
                    log_event(
                        charge_controller.current_stage,
                        v,
                        i,
                        t,
                        ah,
                        "SOFT_WATCHDOG_HA_LOST",
                    )
                except Exception:
                    pass
                await hass.turn_off(ENTITY_MAP["switch"])
                charge_controller.stop()
        except Exception as ex:
            logger.error("soft_watchdog_loop: %s", ex)


async def watchdog_loop() -> None:
    """Hardware Watchdog: при потере связи — аварийное отключение. При U>15В — 60 сек таймаут."""
    global last_chat_id
    while True:
        await asyncio.sleep(30)
        try:
            now = time.time()
            last = charge_controller.last_update_time
            if last <= 0:
                continue
            delta = now - last

            live = await hass.get_all_live()
            v = _safe_float(live.get("voltage"))
            output_on = str(live.get("switch", "")).lower() == "on"

            if not output_on:
                continue

            if delta >= WATCHDOG_TIMEOUT:
                logger.critical("CRITICAL: Watchdog timeout. Emergency shutdown.")
                i = _safe_float(live.get("current"))
                ah = _safe_float(live.get("ah"))
                t = _safe_float(live.get("temp_ext"))
                log_event(
                    charge_controller.current_stage,
                    v,
                    i,
                    t,
                    ah,
                    "WATCHDOG_TIMEOUT",
                )
                await hass.turn_off(ENTITY_MAP["switch"])
                charge_controller.stop()
                continue

            if v > HIGH_V_THRESHOLD and delta >= HIGH_V_FAST_TIMEOUT:
                logger.critical("CRITICAL: Watchdog timeout (high voltage >15V, 60s). Emergency shutdown.")
                i = _safe_float(live.get("current"))
                ah = _safe_float(live.get("ah"))
                t = _safe_float(live.get("temp_ext"))
                log_event(
                    charge_controller.current_stage,
                    v,
                    i,
                    t,
                    ah,
                    "WATCHDOG_HIGH_V",
                )
                await hass.turn_off(ENTITY_MAP["switch"])
                charge_controller.stop()
                charge_controller.emergency_hv_disconnect = True
        except Exception as ex:
            logger.error("watchdog_loop: %s", ex)


async def charge_monitor() -> None:
    """Фоновая задача: раз в 15 мин проверяет ток; алерты при завершении заряда и при нулевом потреблении."""
    global last_chat_id, last_charge_alert_at, last_idle_alert_at, zero_current_since
    while True:
        await asyncio.sleep(15 * 60)
        try:
            live = await hass.get_all_live()
            output_on = str(live.get("switch", "")).lower() == "on"
            battery_v = _safe_float(live.get("battery_voltage"))
            i = _safe_float(live.get("current"))
            now = datetime.now()

            if not output_on:
                zero_current_since = None
                continue

            # Алерт: ток 0.0А более 30 мин при включенном выходе
            if i <= 0.0:
                if zero_current_since is None:
                    zero_current_since = now
                elif (now - zero_current_since).total_seconds() >= ZERO_CURRENT_THRESHOLD_MINUTES * 60:
                    if not last_idle_alert_at or (now - last_idle_alert_at) >= IDLE_ALERT_COOLDOWN:
                        msg = (
                            "⚠️ Выход включен, но потребление отсутствует. "
                            "Не забудьте выключить прибор."
                        )
                        logger.info("Charge monitor (idle): %s", msg)
                        last_idle_alert_at = now
                        if last_chat_id:
                            try:
                                await bot.send_message(last_chat_id, msg, parse_mode=ParseMode.HTML)
                            except Exception:
                                pass
            else:
                zero_current_since = None

            # Алерт: заряд завершён (высокое U на АКБ, низкий I)
            battery_v = _safe_float(live.get("battery_voltage"))
            if battery_v >= 13.5 and i < 0.1:
                if last_charge_alert_at and (now - last_charge_alert_at) < CHARGE_ALERT_COOLDOWN:
                    continue
                msg = (
                    f"⚠️ Заряд завершён или аккумулятор почти полон. "
                    f"Ток упал до {i:.2f}А при напряжении {battery_v:.2f}В."
                )
                logger.info("Charge monitor: %s", msg)
                last_charge_alert_at = now
                if last_chat_id:
                    try:
                        await bot.send_message(last_chat_id, msg, parse_mode=ParseMode.HTML)
                    except Exception:
                        pass
        except Exception as ex:
            logger.error("charge_monitor (сеть/ошибка): %s", ex)
            await asyncio.sleep(60)


async def data_logger() -> None:
    """Фоновая задача: опрос HA каждые 30с, сохранение в DB, ChargeController tick, проверка безопасности."""
    global last_chat_id, last_ha_ok_time, last_checkpoint_time
    while True:
        try:
            live = await hass.get_all_live()
            last_ha_ok_time = time.time()
            battery_v = _safe_float(live.get("battery_voltage"))
            output_v = _safe_float(live.get("voltage"))
            i = _safe_float(live.get("current"))
            p = _safe_float(live.get("power"))
            temp_ext = live.get("temp_ext")
            t = _safe_float(temp_ext)
            ah = _safe_float(live.get("ah"))
            is_cv = str(live.get("is_cv", "")).lower() == "on"
            await add_record(battery_v, i, p, t)

            actions = await charge_controller.tick(battery_v, i, temp_ext, is_cv, ah)

            if actions.get("log_event"):
                log_event(
                    charge_controller.current_stage,
                    battery_v,
                    i,
                    t,
                    ah,
                    actions["log_event"],
                )

            now_ts = time.time()
            if charge_controller.is_active and (now_ts - last_checkpoint_time >= 600):
                log_checkpoint(charge_controller.current_stage, battery_v, i, t, ah)
                last_checkpoint_time = now_ts

            if actions.get("emergency_stop"):
                await hass.turn_off(ENTITY_MAP["switch"])
                if actions.get("full_reset"):
                    charge_controller.full_reset()
                else:
                    charge_controller.stop()
            elif charge_controller.is_active:
                if actions.get("turn_off"):
                    await hass.turn_off(ENTITY_MAP["switch"])
                if actions.get("turn_on"):
                    await hass.turn_on(ENTITY_MAP["switch"])
                if actions.get("set_voltage") is not None:
                    await hass.set_voltage(float(actions["set_voltage"]))
                if actions.get("set_current") is not None:
                    await hass.set_current(float(actions["set_current"]))
                if actions.get("set_ovp") is not None and ENTITY_MAP.get("ovp"):
                    await hass.set_ovp(float(actions["set_ovp"]))
                if actions.get("set_ocp") is not None and ENTITY_MAP.get("ocp"):
                    await hass.set_ocp(float(actions["set_ocp"]))

        except Exception as ex:
            logger.error("data_logger: %s", ex)
        await asyncio.sleep(30)


# --- Handlers ---


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    global last_chat_id
    last_chat_id = message.chat.id
    logger.info("Command /start from %s", message.from_user.id)
    msg_id = await send_dashboard(message)
    if message.from_user:
        user_dashboard[message.from_user.id] = msg_id


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """Статистика и прогноз заряда."""
    global last_chat_id
    last_chat_id = message.chat.id
    try:
        live = await hass.get_all_live()
        battery_v = _safe_float(live.get("battery_voltage"))
        i = _safe_float(live.get("current"))
        ah = _safe_float(live.get("ah"))
        temp = _safe_float(live.get("temp_ext"))
    except Exception as ex:
        logger.error("cmd_stats get_live: %s", ex)
        await message.answer("Ошибка получения данных с HA.")
        return

    if not charge_controller.is_active:
        text = (
            "📊 <b>СТАТИСТИКА ЗАРЯДА</b>\n"
            "──────────────────\n"
            "Заряд не активен.\n"
            f"V: {battery_v:.2f}В | I: {i:.2f}А | Ah: {ah:.2f} | T: {temp:.1f}°C"
        )
        await message.answer(text)
        return

    stats = charge_controller.get_stats(battery_v, i, ah, temp)
    health = stats.get("health_warning")
    text = (
        "📊 <b>СТАТИСТИКА ЗАРЯДА</b>\n"
        "──────────────────\n"
        f"🔋 <b>Этап:</b> {stats['stage']}\n"
        f"⏱ <b>В работе:</b> {stats['elapsed_time']}\n"
        f"📥 <b>Залито:</b> {stats['ah_total']:.2f} Ач\n"
        f"🌡 <b>Темп:</b> {stats['temp_ext']:.1f}°C ({stats['temp_trend']})\n\n"
        "🔮 <b>ПРОГНОЗ:</b>\n"
        f"Завершение через {stats['predicted_time']}\n"
        f"<i>{stats['comment']}</i>"
    )
    if health:
        text += f"\n\n{health}"
    await message.answer(text)


@router.message(F.text)
async def ah_input_handler(message: Message) -> None:
    """Обработка ввода ёмкости АКБ после выбора профиля."""
    global awaiting_ah, last_chat_id, last_checkpoint_time
    user_id = message.from_user.id if message.from_user else 0
    profile = awaiting_ah.get(user_id)
    if not profile:
        return
    text = (message.text or "").strip()
    try:
        ah = int(float(text))
        if ah < 1 or ah > 500:
            await message.answer("Введите число от 1 до 500.")
            return
    except ValueError:
        await message.answer("Введите число (например 60).")
        return
    del awaiting_ah[user_id]
    last_chat_id = message.chat.id

    live = await hass.get_all_live()
    battery_v = _safe_float(live.get("battery_voltage"))
    i = _safe_float(live.get("current"))
    t = _safe_float(live.get("temp_ext"))
    ah_val = _safe_float(live.get("ah"))
    charge_controller.start(profile, ah)
    if battery_v < 12.0:
        await hass.set_voltage(12.0)
        await hass.set_current(0.5)
    else:
        uv, ui = charge_controller._main_target()
        await hass.set_voltage(uv)
        await hass.set_current(ui)
    await hass.turn_on(ENTITY_MAP["switch"])
    last_checkpoint_time = time.time()
    log_event("Подготовка", battery_v, i, t, ah_val, f"START profile={profile} ah={ah}")
    await message.answer(
        f"<b>✅ Заряд запущен:</b> {profile} {ah}Ач\n"
        f"Текущая фаза: <b>{charge_controller.current_stage}</b>",
        parse_mode=ParseMode.HTML,
    )
    old_id = user_dashboard.get(user_id)
    await send_dashboard(message, old_msg_id=old_id)


@router.callback_query(F.data == "charge_modes")
async def charge_modes_handler(call: CallbackQuery) -> None:
    """Открыть подменю «🚗 Авто» с режимами заряда."""
    global last_chat_id
    last_chat_id = call.message.chat.id
    warning = (
        "⚠️ <b>ВНИМАНИЕ:</b> Данные режимы используют напряжение до 16.5В. "
        "Убедитесь, что АКБ отсоединена от бортовой сети автомобиля!"
    )
    ikb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🟦 Ca/Ca", callback_data="profile_caca"),
                InlineKeyboardButton(text="🟧 EFB", callback_data="profile_efb"),
                InlineKeyboardButton(text="🟥 AGM", callback_data="profile_agm"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="charge_back")],
        ]
    )
    try:
        await call.message.edit_caption(
            caption=f"<b>🚗 Авто</b>\n\n{warning}\n\nВыберите профиль заряда:",
            reply_markup=ikb,
        )
    except Exception:
        await call.message.edit_text(
            f"<b>🚗 Авто</b>\n\n{warning}\n\nВыберите профиль заряда:",
            reply_markup=ikb,
        )
    await call.answer()


@router.callback_query(F.data == "charge_back")
async def charge_back_handler(call: CallbackQuery) -> None:
    """Вернуться из подменю «🚗 Авто» в главное меню."""
    old_id = user_dashboard.get(call.from_user.id) if call.from_user else None
    await send_dashboard(call, old_msg_id=old_id)
    await call.answer()


@router.callback_query(F.data == "refresh")
async def refresh_handler(call: CallbackQuery) -> None:
    global last_chat_id
    last_chat_id = call.message.chat.id
    old_id = user_dashboard.get(call.from_user.id) if call.from_user else None
    await send_dashboard(call, old_msg_id=old_id)
    await call.answer("Данные обновлены")


@router.callback_query(F.data == "power_toggle")
async def power_toggle_handler(call: CallbackQuery) -> None:
    global last_chat_id
    last_chat_id = call.message.chat.id
    live = await hass.get_all_live()
    is_on = str(live.get("switch", "")).lower() == "on"
    if is_on:
        await hass.turn_off()
    else:
        await hass.turn_on()
    await asyncio.sleep(1)
    old_id = user_dashboard.get(call.from_user.id) if call.from_user else None
    await send_dashboard(call, old_msg_id=old_id)
    await call.answer("Питание " + ("включено" if not is_on else "выключено"))


@router.callback_query(F.data.in_({"profile_caca", "profile_efb", "profile_agm"}))
async def profile_selection(call: CallbackQuery) -> None:
    global awaiting_ah, last_chat_id
    last_chat_id = call.message.chat.id
    mapping = {"profile_caca": "Ca/Ca", "profile_efb": "EFB", "profile_agm": "AGM"}
    profile = mapping.get(call.data, "Ca/Ca")
    user_id = call.from_user.id if call.from_user else 0
    awaiting_ah[user_id] = profile
    await call.message.answer(
        f"<b>Профиль {profile}</b> выбран.\n\n"
        "Введите ёмкость аккумулятора в Ah (например, 60):",
        parse_mode=ParseMode.HTML,
    )
    await call.answer()


@router.callback_query(F.data == "charge_stop")
async def charge_stop_handler(call: CallbackQuery) -> None:
    global last_chat_id
    last_chat_id = call.message.chat.id
    charge_controller.stop()
    await hass.turn_off(ENTITY_MAP["switch"])
    await call.message.answer("<b>🛑 Заряд остановлен.</b> Выход выключен.")
    old_id = user_dashboard.get(call.from_user.id) if call.from_user else None
    await send_dashboard(call, old_msg_id=old_id)
    await call.answer()


@router.callback_query(F.data == "logs")
async def logs_handler(call: CallbackQuery) -> None:
    times, voltages, currents, temps = await get_logs_data(limit=5)
    if not times:
        text = "<b>📈 Последние логи</b>\n\nНет данных."
    else:
        header = "Время   | Напряж. | Ток    | Темп\n--------+---------+--------+-------"
        lines = [header]
        for j in range(min(5, len(times))):
            ts = _format_time(times[j])
            v = voltages[j] if j < len(voltages) else 0.0
            i = currents[j] if j < len(currents) else 0.0
            t = temps[j] if j < len(temps) else 0.0
            lines.append(f"{ts} | {v:5.2f}В | {i:5.2f}А | {t:5.1f}°C")
        text = "<b>📈 Последние логи</b>\n\n<pre>" + "\n".join(lines) + "</pre>"
    await call.message.answer(text, parse_mode=ParseMode.HTML)
    await call.answer()


@router.callback_query(F.data == "ai_analysis")
async def ai_analysis_handler(call: CallbackQuery) -> None:
    await call.answer()
    status_msg = await call.message.answer("⏳ Анализирую...", parse_mode=ParseMode.HTML)
    times, voltages, currents = await get_raw_history(limit=50)
    trend_summary = _build_trend_summary(times, voltages, currents)
    history = {
        "times": times,
        "voltages": voltages,
        "currents": currents,
        "trend_summary": trend_summary,
    }
    result = await ask_deepseek(history)
    result_html = _md_to_html(result)
    await status_msg.edit_text(f"<b>🧠 AI Анализ:</b>\n{result_html}", parse_mode=ParseMode.HTML)


async def main() -> None:
    await init_db()
    rotate_if_needed()

    # Auto-Resume: восстановить сессию, если charge_session.json < 60 мин
    global last_checkpoint_time
    try:
        live = await hass.get_all_live()
        battery_v = _safe_float(live.get("battery_voltage"))
        i = _safe_float(live.get("current"))
        ah = _safe_float(live.get("ah"))
        ok, msg = charge_controller.try_restore_session(battery_v, i, ah)
        if ok and msg:
            last_checkpoint_time = time.time()
            if charge_controller.current_stage == charge_controller.STAGE_SAFE_WAIT:
                uv, ui = charge_controller._safe_wait_target_v, charge_controller._safe_wait_target_i
                await hass.set_voltage(uv)
                await hass.set_current(ui)
                # Output остаётся выключен — ждём падения V
            else:
                uv, ui = charge_controller._get_target_v_i()
                await hass.set_voltage(uv)
                await hass.set_current(ui)
                await hass.turn_on(ENTITY_MAP["switch"])
            t_ext = _safe_float(live.get("temp_ext"))
            log_event(
                charge_controller.current_stage,
                battery_v,
                i,
                t_ext,
                ah,
                "RESTORE",
            )
            _charge_notify(msg)
            logger.info("Session restored: %s", charge_controller.current_stage)
    except Exception as ex:
        logger.warning("Auto-resume check failed: %s", ex)

    dp.include_router(router)
    await bot.set_my_commands([
        BotCommand(command="start", description="Открыть дашборд RD6018"),
        BotCommand(command="stats", description="Статистика и прогноз заряда"),
    ])
    asyncio.create_task(data_logger())
    asyncio.create_task(charge_monitor())
    asyncio.create_task(soft_watchdog_loop())
    asyncio.create_task(watchdog_loop())
    logger.info("RD6018 bot starting")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
