"""
bot.py — RD6018 Ultimate Telegram Controller (Async Edition).
Дашборд: один автообновляемый message с графиком, метриками и кнопками.
"""
import asyncio
import json
import logging
import re
import time

import aiohttp
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
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, ENTITY_MAP, HA_URL, HA_TOKEN, TG_TOKEN
from database import add_record, get_graph_data, get_logs_data, get_raw_history, init_db
from graphing import generate_chart
from hass_api import HassClient
from time_utils import format_time_user_tz

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


async def call_llm_analytics(data: dict) -> Optional[str]:
    """Запрос к DeepSeek для анализа телеметрии. Возвращает комментарий или None."""
    if not DEEPSEEK_API_KEY:
        return None
    data_str = json.dumps(data, ensure_ascii=False, indent=2)
    system_prompt = (
        "Ты — эксперт по свинцово-кислотным аккумуляторам. "
        "Анализируй телеметрию и давай краткий технический вердикт."
    )
    user_prompt = (
        f"Данные: {data_str}\n\n"
        "Оцени состояние АКБ, укажи на аномалии и дай прогноз окончания этапа одним предложением. "
        "Ответь на русском. Используй HTML: <b>жирный</b>, <i>курсив</i>."
    )
    url = f"{DEEPSEEK_BASE_URL.rstrip('/')}/v1/chat/completions"
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 256,
        "temperature": 0.3,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    logger.warning("DeepSeek analytics API %d", resp.status)
                    return None
                result = await resp.json()
                choices = result.get("choices", [])
                if not choices:
                    return None
                content = choices[0].get("message", {}).get("content", "").strip()
                return content if content else None
    except Exception as ex:
        logger.warning("call_llm_analytics: %s", ex)
        return None


charge_controller = ChargeController(hass, notify_cb=_charge_notify)

user_dashboard: Dict[int, int] = {}
last_chat_id: Optional[int] = None
last_charge_alert_at: Optional[datetime] = None
last_idle_alert_at: Optional[datetime] = None
zero_current_since: Optional[datetime] = None
CHARGE_ALERT_COOLDOWN = timedelta(hours=1)
IDLE_ALERT_COOLDOWN = timedelta(hours=1)
ZERO_CURRENT_THRESHOLD_MINUTES = 30
awaiting_ah: Dict[int, str] = {}
last_ha_ok_time: float = 0.0
link_lost_alert_sent: bool = False  # флаг-блокировка однократного уведомления о потере связи
SOFT_WATCHDOG_TIMEOUT = 3 * 60
last_checkpoint_time: float = 0.0


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
    """Преобразовать ISO timestamp в HH:MM:SS с пользовательским часовым поясом."""
    if not ts:
        return "?:?:?"
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00")[:19])
        if dt.tzinfo is None:
            import pytz
            dt = dt.replace(tzinfo=pytz.UTC)
        return format_time_user_tz(dt)
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

    # Новая структура интерфейса
    
    # 1. ПЕРВАЯ СТРОКА (Общий статус)
    if charge_controller.is_active:
        timers = charge_controller.get_timers()
        status_emoji = "⚡️" if is_on else "⏸️"
        stage_name = charge_controller.current_stage
        battery_type = charge_controller.battery_type
        total_time = timers['total_time']
        status_line = f"📊 СТАТУС: {status_emoji} {stage_name} | {battery_type} | ⏱ {total_time}"
    else:
        status_line = f"📊 СТАТУС: 💤 Ожидание | АКБ: {battery_v:.2f}В"
    
    # 2. ВТОРАЯ СТРОКА (Живые данные)
    temp_warning = ""
    if temp_int > 50.0:
        temp_warning = f" | ⚠️ Блок: {temp_int:.1f}°C"
    live_line = f"⚡️ LIVE: {battery_v:.2f}В | {i:.2f}А | 🌡 {temp_ext:.1f}°C{temp_warning}"
    
    # 3. БЛОК ЦЕЛИ (Две строки) - только при активном заряде
    stage_block = ""
    if charge_controller.is_active:
        stage_time = timers['stage_time']
        time_limit = timers['remaining_time'] if timers['remaining_time'] != "—" else "∞"
        stage_block = (
            f"\n📍 ЭТАП: {stage_name} ({stage_time})\n"
            f"🎯 ЦЕЛЬ: {set_v:.2f}В | {set_i:.1f}А | Лимит: {time_limit}"
        )
    
    # 4. ЧЕТВЕРТАЯ СТРОКА (Емкость)
    capacity_line = f"🔋 ЕМКОСТЬ: {ah:.2f} Ач"
    
    # Формируем итоговый текст
    text = f"{status_line}\n{live_line}{stage_block}\n{capacity_line}"

    times, voltages, currents = await get_graph_data(limit=100)
    buf = generate_chart(times, voltages, currents)
    photo = BufferedInputFile(buf.getvalue(), filename="chart.png") if buf else None

    # Новое кнопочное меню
    # Кнопка-хамелеон: зависит только от output_on (HA switch)
    main_btn_text = "🛑 ОСТАНОВИТЬ" if is_on else "🚀 ЗАПУСТИТЬ"

    # Новая структура клавиатуры:
    # Row 1: [🔄 ОБНОВИТЬ ИНФОРМАЦИЮ] (Full width)
    # Row 2: Динамическая кнопка [🛑 ОСТАНОВИТЬ] / [🚀 ЗАПУСТИТЬ]
    # Row 3: [🧠 AI АНАЛИЗ] | [⚙️ РЕЖИМЫ]
    # Row 4: [📝 ЛОГИ СОБЫТИЙ]
    kb_rows = [
        [InlineKeyboardButton(text="🔄 ОБНОВИТЬ ИНФОРМАЦИЮ", callback_data="refresh")],
        [InlineKeyboardButton(text=main_btn_text, callback_data="power_toggle")],
        [
            InlineKeyboardButton(text="🧠 AI АНАЛИЗ", callback_data="ai_analysis"),
            InlineKeyboardButton(text="⚙️ РЕЖИМЫ", callback_data="charge_modes"),
        ],
        [InlineKeyboardButton(text="📝 ЛОГИ СОБЫТИЙ", callback_data="logs")],
    ]
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
    global last_chat_id, last_ha_ok_time, last_checkpoint_time, link_lost_alert_sent
    while True:
        try:
            live = await hass.get_all_live()
            last_ha_ok_time = time.time()
            link_lost_alert_sent = False  # сброс флага при успешном подключении
            
            battery_v = _safe_float(live.get("battery_voltage"))
            output_v = _safe_float(live.get("voltage"))
            i = _safe_float(live.get("current"))
            p = _safe_float(live.get("power"))
            temp_ext = live.get("temp_ext")
            t = _safe_float(temp_ext)
            ah = _safe_float(live.get("ah"))
            is_cv = str(live.get("is_cv", "")).lower() == "on"
            output_switch = live.get("switch")
            
            # v2.5 Умный watchdog: обновляем последнее известное состояние выхода
            if output_switch is not None and str(output_switch).lower() not in ("unavailable", "unknown", ""):
                charge_controller._last_known_output_on = (
                    output_switch is True or str(output_switch).lower() == "on"
                )
            
            await add_record(battery_v, i, p, t)

            # Восстановление после потери связи: если был unavailable и теперь данные есть — попробовать restore
            if temp_ext is not None and temp_ext not in ("unavailable", "unknown", ""):
                if charge_controller._was_unavailable and charge_controller.current_stage == charge_controller.STAGE_IDLE:
                    ok, msg = charge_controller.try_restore_session(battery_v, i, ah)
                    if ok and msg:
                        last_checkpoint_time = time.time()
                        if charge_controller.current_stage == charge_controller.STAGE_SAFE_WAIT:
                            uv, ui = charge_controller._safe_wait_target_v, charge_controller._safe_wait_target_i
                            await hass.set_voltage(uv)
                            await hass.set_current(ui)
                        else:
                            uv, ui = charge_controller._get_target_v_i()
                            await hass.set_voltage(uv)
                            await hass.set_current(ui)
                            await hass.turn_on(ENTITY_MAP["switch"])
                        log_event(
                            charge_controller.current_stage,
                            battery_v,
                            i,
                            t,
                            ah,
                            "RESTORE",
                        )
                        _charge_notify(msg)
                        logger.info("Session restored after link recovery: %s", charge_controller.current_stage)

            actions = await charge_controller.tick(battery_v, i, temp_ext, is_cv, ah, output_switch)

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
                # иначе контроллер уже сделал stop(clear_session=False) — сессия сохранена для restore при возврате связи
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
            err_str = str(ex).lower()
            if "name resolution" in err_str or "dns" in err_str or "nodename" in err_str:
                logger.warning("data_logger (DNS/сеть): %s", ex)
            else:
                logger.error("data_logger: %s", ex)
            
            # v2.5 Умный watchdog: поведение зависит от последнего состояния выхода
            output_was_on = charge_controller._last_known_output_on
            
            if not output_was_on:
                # Выход был выключен — тихий переход в IDLE, без уведомлений
                if charge_controller.is_active:
                    charge_controller.stop(clear_session=False)
                    logger.info("Link lost with output OFF: quiet transition to IDLE")
            else:
                # Выход был включён — однократное уведомление и аварийное отключение
                if not link_lost_alert_sent:
                    _charge_notify("🚨 Связь потеряна во время активного заряда!")
                    link_lost_alert_sent = True
                    logger.critical("Link lost during active charge: emergency shutdown")
                
                try:
                    await hass.turn_off(ENTITY_MAP["switch"])
                except Exception:
                    pass
                
                if charge_controller.is_active:
                    charge_controller.stop(clear_session=False)
                    log_event(
                        "EMERGENCY",
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        "LINK_LOST_DURING_CHARGE",
                    )
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
    """Статистика и прогноз заряда с AI-аналитикой."""
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
    tech_block = (
        "📊 <b>СТАТИСТИКА ЗАРЯДА</b>\n"
        "──────────────────\n"
        f"🔋 <b>Этап:</b> {stats['stage']}\n"
        f"⏱ <b>В работе:</b> {stats['elapsed_time']}\n"
        f"📥 <b>Залито:</b> {stats['ah_total']:.2f} Ач\n"
        f"🌡 <b>Темп:</b> {stats['temp_ext']:.1f}°C ({stats['temp_trend']})\n\n"
        "🔮 <b>ПРОГНОЗ:</b>\n"
        f"Завершение через {stats['predicted_time']}\n"
        f"<i>{stats['comment']}</i>\n\n"
    )
    ai_placeholder = "🤖 <b>Аналитика DeepSeek:</b> Думаю..."
    text = tech_block + ai_placeholder
    if health:
        text += f"\n\n{health}"
    sent = await message.answer(text)

    # Принудительное обновление сенсоров перед формированием промпта для DeepSeek
    try:
        live = await hass.get_all_live()
        battery_v = _safe_float(live.get("battery_voltage"))
        i = _safe_float(live.get("current"))
        ah = _safe_float(live.get("ah"))
        temp = _safe_float(live.get("temp_ext"))
    except Exception as ex:
        logger.warning("cmd_stats update_sensors: %s", ex)
    telemetry = charge_controller.get_telemetry_summary(battery_v, i, ah, temp)
    ai_comment = await call_llm_analytics(telemetry)
    if ai_comment:
        new_text = tech_block + f"🤖 <b>Аналитика DeepSeek:</b>\n<i>{ai_comment}</i>"
    else:
        new_text = tech_block + "🤖 <b>Аналитика DeepSeek:</b> <i>Математический прогноз (API недоступен)</i>"
    if health:
        new_text += f"\n\n{health}"
    try:
        await sent.edit_text(new_text, parse_mode=ParseMode.HTML)
    except Exception as ex:
        logger.warning("cmd_stats edit_text: %s", ex)


async def get_current_context_for_llm() -> str:
    """v2.6 Получить расширенный контекст для LLM: таймеры, параметры RD6018, события."""
    try:
        live = await hass.get_all_live()
        battery_v = _safe_float(live.get("battery_voltage"))
        output_v = _safe_float(live.get("voltage"))
        i = _safe_float(live.get("current"))
        p = _safe_float(live.get("power"))
        temp_ext = _safe_float(live.get("temp_ext"))
        set_v = _safe_float(live.get("set_voltage"))
        set_i = _safe_float(live.get("set_current"))
        is_on = str(live.get("switch", "")).lower() == "on"
        is_cv = str(live.get("is_cv", "")).lower() == "on"
        is_cc = str(live.get("is_cc", "")).lower() == "on"
        mode = "CV" if is_cv else ("CC" if is_cc else "—")
        
        # v2.6 Данные таймеров
        timers = charge_controller.get_timers()
        timer_info = ""
        if charge_controller.is_active:
            timer_info = f"""
- Общее время заряда: {timers['total_time']}
- Время в этапе {charge_controller.current_stage}: {timers['stage_time']}
- Лимит этапа: {timers['remaining_time']} осталось"""
        
        context = f"""Текущие параметры RD6018:
- Напряжение АКБ: {battery_v:.2f}В
- Напряжение выхода: {output_v:.2f}В  
- Ток: {i:.2f}А
- Мощность: {p:.2f}Вт
- Температура внешняя: {temp_ext:.1f}°C
- Настройки: V_set={set_v:.2f}В, I_set={set_i:.2f}А
- Режим: {mode}
- Статус выхода: {'ON' if is_on else 'OFF'}
- Стадия заряда: {charge_controller.current_stage}
- Тип АКБ: {charge_controller.battery_type if charge_controller.is_active else 'не выбран'}
- Ёмкость: {charge_controller.ah_capacity}Ач{timer_info}"""
        
        # Последние события из лога
        from charging_log import get_recent_events
        recent_events = get_recent_events(5)
        if recent_events:
            context += "\n\nПоследние события:\n"
            for event in recent_events:
                context += f"- {event}\n"
        
        return context
    except Exception as ex:
        return f"Ошибка получения контекста: {ex}"


@router.message(F.text)
async def text_message_handler(message: Message) -> None:
    """v2.6 Обработка текстовых сообщений: ввод ёмкости АКБ или режим диалога с LLM."""
    global awaiting_ah, last_chat_id, last_checkpoint_time
    user_id = message.from_user.id if message.from_user else 0
    profile = awaiting_ah.get(user_id)
    
    # Если ожидаем ввод ёмкости АКБ
    if profile:
        await handle_ah_input(message, profile, user_id)
        return
    
    # v2.6 Режим диалога: отправляем сообщение в LLM с контекстом
    await handle_dialog_mode(message)


async def handle_ah_input(message: Message, profile: str, user_id: int) -> None:
    """Обработка ввода ёмкости АКБ после выбора профиля."""
    global awaiting_ah, last_chat_id, last_checkpoint_time
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


async def handle_dialog_mode(message: Message) -> None:
    """v2.6 Режим диалога: отправка сообщения пользователя в LLM с текущим контекстом."""
    if not DEEPSEEK_API_KEY:
        await message.answer("🤖 AI-консультант недоступен (не настроен API ключ)")
        return
    
    user_question = (message.text or "").strip()
    if not user_question:
        return
    
    # Показываем что бот думает
    thinking_msg = await message.answer("🤖 Анализирую данные...")
    
    try:
        # Получаем текущий контекст
        context = await get_current_context_for_llm()
        
        # Системный промпт для эксперта-аккумуляторщика
        system_prompt = """Ты — эксперт по свинцово-кислотным аккумуляторам и системам заряда RD6018. 
Отвечай как опытный аккумуляторщик, поясняй текущие процессы, диагностируй проблемы.
Используй HTML разметку: <b>жирный</b>, <i>курсив</i>, <code>моноширинный</code>.
Отвечай кратко и по существу на русском языке."""
        
        user_prompt = f"""Контекст системы:
{context}

Вопрос пользователя: {user_question}

Проанализируй ситуацию и дай экспертный ответ."""

        # Вызов LLM
        url = f"{DEEPSEEK_BASE_URL.rstrip('/')}/v1/chat/completions"
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 512,
            "temperature": 0.3,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status != 200:
                    await thinking_msg.edit_text("🤖 Ошибка API. Попробуйте позже.")
                    return
                
                result = await resp.json()
                choices = result.get("choices", [])
                if not choices:
                    await thinking_msg.edit_text("🤖 Нет ответа от AI.")
                    return
                
                ai_response = choices[0].get("message", {}).get("content", "").strip()
                if not ai_response:
                    await thinking_msg.edit_text("🤖 Пустой ответ от AI.")
                    return
                
                # Отправляем ответ
                await thinking_msg.edit_text(
                    f"🤖 <b>AI-Консультант:</b>\n\n{ai_response}",
                    parse_mode=ParseMode.HTML
                )
                
    except Exception as ex:
        logger.error("handle_dialog_mode: %s", ex)
        await thinking_msg.edit_text("🤖 Ошибка при обращении к AI-консультанту.")


@router.callback_query(F.data == "charge_modes")
async def charge_modes_handler(call: CallbackQuery) -> None:
    """Открыть подменю «🚗 Авто» с режимами заряда."""
    try:
        await call.answer()
    except Exception:
        pass
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


@router.callback_query(F.data == "charge_back")
async def charge_back_handler(call: CallbackQuery) -> None:
    """Вернуться из подменю «🚗 Авто» в главное меню."""
    try:
        await call.answer()
    except Exception:
        pass
    old_id = user_dashboard.get(call.from_user.id) if call.from_user else None
    await send_dashboard(call, old_msg_id=old_id)


@router.callback_query(F.data == "refresh")
async def refresh_handler(call: CallbackQuery) -> None:
    try:
        await call.answer("Информация обновлена")
    except Exception:
        pass
    global last_chat_id
    last_chat_id = call.message.chat.id
    old_id = user_dashboard.get(call.from_user.id) if call.from_user else None
    await send_dashboard(call, old_msg_id=old_id)


@router.callback_query(F.data == "power_toggle")
async def power_toggle_handler(call: CallbackQuery) -> None:
    try:
        await call.answer()
    except Exception:
        pass
    global last_chat_id
    last_chat_id = call.message.chat.id
    live = await hass.get_all_live()
    is_on = str(live.get("switch", "")).lower() == "on"
    # Если заряд активен или выход включен — останавливаем заряд и выключаем выход
    if charge_controller.is_active or is_on:
        charge_controller.stop()
        await hass.turn_off(ENTITY_MAP["switch"])
        await call.message.answer(
            "<b>🛑 Заряд остановлен.</b> Выход выключен.",
            parse_mode=ParseMode.HTML,
        )
    else:
        # Заряд стоит: включаем выход с текущими параметрами RD6018
        await hass.turn_on(ENTITY_MAP["switch"])
        await call.message.answer(
            "<b>🚀 Заряд запущен.</b> Выход включен с текущими параметрами.",
            parse_mode=ParseMode.HTML,
        )
    await asyncio.sleep(1)
    old_id = user_dashboard.get(call.from_user.id) if call.from_user else None
    await send_dashboard(call, old_msg_id=old_id)


@router.callback_query(F.data.in_({"profile_caca", "profile_efb", "profile_agm"}))
async def profile_selection(call: CallbackQuery) -> None:
    try:
        await call.answer()
    except Exception:
        pass
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


@router.callback_query(F.data == "logs")
async def logs_handler(call: CallbackQuery) -> None:
    try:
        await call.answer()
    except Exception:
        pass
    times, voltages, currents, temps = await get_logs_data(limit=5)
    if not times:
        text = "<b>📝 Логи событий</b>\n\nНет данных."
    else:
        header = "Время   | Напряж. | Ток    | Темп\n--------+---------+--------+-------"
        lines = [header]
        for j in range(min(5, len(times))):
            ts = _format_time(times[j])
            v = voltages[j] if j < len(voltages) else 0.0
            i = currents[j] if j < len(currents) else 0.0
            t = temps[j] if j < len(temps) else 0.0
            lines.append(f"{ts} | {v:5.2f}В | {i:5.2f}А | {t:5.1f}°C")
        text = "<b>📝 Логи событий</b>\n\n<pre>" + "\n".join(lines) + "</pre>"
    await call.message.answer(text, parse_mode=ParseMode.HTML)


@router.callback_query(F.data == "ai_analysis")
async def ai_analysis_handler(call: CallbackQuery) -> None:
    try:
        await call.answer()
    except Exception:
        pass
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