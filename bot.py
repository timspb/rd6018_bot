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
from typing import Dict, Optional, Union, Any

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
from database import add_record, cleanup_old_records, get_graph_data, get_logs_data, get_raw_history, init_db
from graphing import generate_chart
from hass_api import HassClient
from time_utils import format_time_user_tz
from concurrent.futures import ThreadPoolExecutor
import requests
import html

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

# Executor для блокирующих операций (DeepSeek API)
executor = ThreadPoolExecutor(max_workers=2)


def _call_deepseek_sync(system_prompt: str, user_prompt: str) -> str:
    """Синхронный вызов DeepSeek API для использования в executor."""
    import requests
    
    try:
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
        
        response = requests.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=20
        )
        
        if response.status_code != 200:
            return f"ERROR: API вернул статус {response.status_code}"
        
        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            return "ERROR: Пустой ответ от DeepSeek API"
        
        ai_response = choices[0].get("message", {}).get("content", "").strip()
        return ai_response or "ERROR: Пустой контент от AI"
        
    except Exception as ex:
        logger.error("DeepSeek sync call failed: %s", ex)
        return f"ERROR: Ошибка при обращении к AI - {ex}"


def _charge_notify(msg: str) -> None:
    """Отправка уведомления от ChargeController в Telegram."""
    global last_chat_id
    if last_chat_id and msg:
        asyncio.create_task(_send_notify_safe(msg))


async def _send_notify_safe(msg: str) -> None:
    try:
        # Экранируем HTML в уведомлениях, но сохраняем основные теги
        safe_msg = msg
        if not any(tag in msg for tag in ['<b>', '<i>', '<code>']):
            # Если нет HTML тегов, экранируем полностью
            safe_msg = html.escape(msg)
        await bot.send_message(last_chat_id, safe_msg, parse_mode=ParseMode.HTML)
    except Exception as ex:
        logger.error("charge notify failed: %s", ex)
        # Fallback: отправляем без HTML парсинга
        try:
            await bot.send_message(last_chat_id, html.escape(msg))
        except Exception as ex2:
            logger.error("fallback notify also failed: %s", ex2)


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
# FSM для ручного режима
custom_mode_state: Dict[int, str] = {}  # состояние диалога: "voltage", "current", "delta", "time_limit", "capacity"
custom_mode_data: Dict[int, Dict[str, float]] = {}  # накопленные данные пользователя
custom_mode_confirm: Dict[int, Dict[str, Any]] = {}  # данные для подтверждения опасных значений
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


def format_electrical_data(v: float, i: float, p: float = None, precision: int = 2) -> str:
    """Форматтер для электрических данных V/I/P с HTML-экранированием и точностью .2f."""
    result = f"{v:.2f}В | {i:.2f}А"  # Принудительно .2f для всех V/I
    if p is not None:
        result += f" | {p:.1f}Вт"
    return html.escape(result)


def format_temperature_data(t_ext: float, t_int: float = None, warn_threshold: float = 50.0) -> str:
    """Форматтер для температурных данных с предупреждениями и HTML-экранированием."""
    result = f"🌡 {t_ext:.1f}°C"
    if t_int is not None and t_int > warn_threshold:
        result += f" | ⚠️ Блок: {t_int:.1f}°C"
    return html.escape(result)


def format_status_data(is_on: bool, mode: str, stage: str = None) -> str:
    """Форматтер для статусных данных с HTML-экранированием."""
    status_emoji = "⚡️" if is_on else "⏸️"
    result = f"{status_emoji} {mode}"
    if stage:
        result += f" | {html.escape(stage)}"
    return result


def safe_html_format(template: str, **kwargs) -> str:
    """Безопасное форматирование HTML с экранированием переменных."""
    # Экранируем все переменные, кроме тех что уже содержат HTML теги
    safe_kwargs = {}
    for key, value in kwargs.items():
        if isinstance(value, str) and ('<' in value or '>' in value or '&' in value):
            # Если значение уже содержит HTML теги, не экранируем
            if not any(tag in value for tag in ['<b>', '<i>', '<code>', '</b>', '</i>', '</code>']):
                safe_kwargs[key] = html.escape(value)
            else:
                safe_kwargs[key] = value
        else:
            safe_kwargs[key] = html.escape(str(value)) if value is not None else ""
    
    return template.format(**safe_kwargs)


def format_log_event(event_line: str) -> str:
    """Форматирование строки события в красивый вид с иконками."""
    try:
        # Парсим строку формата: [2024-02-12 19:15:23] | Main Charge  | 14.80 | 2.40 | 25.1 |  60.25 | START profile=EFB ah=60
        parts = event_line.split(' | ')
        if len(parts) < 6:
            return f"<code>{html.escape(event_line)}</code>"
        
        timestamp = parts[0].strip('[]')
        stage = parts[1].strip()
        voltage = parts[2].strip()
        current = parts[3].strip()
        temp = parts[4].strip()
        ah = parts[5].strip()
        event = parts[6].strip() if len(parts) > 6 else ""
        
        # Извлекаем только время (ЧЧ:ММ)
        time_only = timestamp.split(' ')[1][:5] if ' ' in timestamp else timestamp[-8:-3]
        
        # Определяем иконку по типу события
        icon = "📋"
        if "START" in event:
            icon = "🏁"
        elif "MAIN" in event or "MIX" in event or "DESULFATION" in event:
            icon = "📈"
        elif "DONE" in event or "FINISH" in event:
            icon = "✅"
        elif "STOP" in event or "EMERGENCY" in event:
            icon = "🛑"
        elif "WARNING" in event or "TEMP" in event:
            icon = "⚠️"
        elif "CHECKPOINT" in event:
            icon = "⏱️"
        elif any(word in event for word in ["Set", "УСТАВКА", "V=", "I="]):
            icon = "⚙️"
        
        # Сокращаем название этапа
        stage_short = stage.replace("Main Charge", "Main").replace("Десульфатация", "Desulf").replace("Безопасное ожидание", "Wait")
        
        # Формируем компактную строку
        if "CHECKPOINT" not in event:  # Скрываем обычные чекпоинты
            # СНАЧАЛА экранируем, ПОТОМ обрезаем - чтобы не порвать HTML теги
            event_clean = event.replace("profile=", "").replace("ah=", "Ah:")
            event_escaped = html.escape(event_clean)
            stage_escaped = html.escape(stage_short)
            
            if len(event_escaped) > 40:
                event_escaped = event_escaped[:37] + "..."
            
            return f"<code>[{time_only}]</code> {icon} <b>{stage_escaped}</b>: {event_escaped}"
        else:
            return ""  # Пропускаем чекпоинты для компактности
            
    except Exception as ex:
        logger.error("Failed to format log event: %s", ex)
        return f"<code>{html.escape(event_line[:100])}</code>"


async def send_dashboard(message_or_call: Union[Message, CallbackQuery], old_msg_id: Optional[int] = None) -> int:
    """
    Сформировать и отправить дашборд.
    Anti-spam: при refresh удаляем старый message перед отправкой нового.
    """
    msg = message_or_call.message if isinstance(message_or_call, CallbackQuery) else message_or_call
    chat_id = msg.chat.id
    user_id = message_or_call.from_user.id if getattr(message_or_call, "from_user", None) else 0

    try:
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
    except Exception as ex:
        logger.error("Failed to get HA data for dashboard: %s", ex)
        # Fallback значения при недоступности HA
        battery_v = output_v = v = i = p = ah = wh = temp_int = temp_ext = set_v = set_i = 0.0
        is_on = is_cv = is_cc = False
        mode = "ERROR"

    # Новая структура интерфейса
    
    # 1. ПЕРВАЯ СТРОКА (Общий статус)
    if charge_controller.is_active:
        timers = charge_controller.get_timers()
        status_emoji = "⚡️" if is_on else "⏸️"
        stage_name = html.escape(charge_controller.current_stage)
        battery_type = html.escape(charge_controller.battery_type)
        total_time = html.escape(timers['total_time'])
        status_line = f"📊 СТАТУС: {status_emoji} {stage_name} | {battery_type} | ⏱ {total_time}"
    else:
        status_line = f"📊 СТАТУС: 💤 Ожидание | АКБ: {battery_v:.2f}В"
    
    # 2. ВТОРАЯ СТРОКА (Живые данные)
    electrical_data = format_electrical_data(battery_v, i)
    temp_data = format_temperature_data(temp_ext, temp_int)
    live_line = f"⚡️ LIVE: {electrical_data} | {temp_data}"
    
    # 3. БЛОК ЭТАПА (Три строки) - только при активном заряде
    stage_block = ""
    if charge_controller.is_active:
        stage_time = timers['stage_time']
        
        # Получаем ТЕКУЩИЕ уставки, которые реально установлены на приборе
        current_v_set = _safe_float(live.get("set_voltage", set_v))  # Текущая уставка напряжения
        current_i_set = _safe_float(live.get("set_current", set_i))  # Текущая уставка тока
        
        # Компактное условие перехода с HTML-безопасными символами
        transition_condition = ""
        raw_stage = charge_controller.current_stage
        time_limit = timers['remaining_time']
        
        if "Main" in raw_stage:
            if charge_controller.battery_type == "Custom":
                delta = charge_controller._custom_delta_threshold
                transition_condition = f"🔜 ФИНИШ: dV/dI &gt; {delta:.3f}"
            elif charge_controller.battery_type in ["Ca/Ca", "EFB"]:
                transition_condition = "🔜 ПЕРЕХОД: &lt;0.3A (40м)"
            elif charge_controller.battery_type == "AGM":
                transition_condition = "🔜 ПЕРЕХОД: &lt;0.2A"
        elif "Mix" in raw_stage:
            transition_condition = "🔜 ФИНИШ: dV&gt;0.03В или dI&gt;0.03А"
        elif "Десульфатация" in raw_stage:
            transition_condition = "🔜 ПЕРЕХОД: 2ч → Main"
        elif "Безопасное ожидание" in raw_stage:
            transition_condition = "🔜 ПЕРЕХОД: падение V"
        elif "Остывание" in raw_stage:
            transition_condition = f"🔜 ВОЗВРАТ: T&le;35°C (сейчас {temp_ext:.1f}°C)"
        
        # Добавляем актуальный лимит времени в часах (убираем минуты)
        if time_limit != "—":
            # Парсим время и оставляем только часы
            try:
                if ":" in time_limit:
                    hours = int(time_limit.split(":")[0])
                    time_display = f"{hours}ч" if hours > 0 else "менее 1ч"
                else:
                    time_display = time_limit
            except:
                time_display = time_limit
                
            if transition_condition:
                transition_condition += f" | Ост: {time_display}"
            else:
                transition_condition = f"🔜 Ост: {time_display}"
        
        stage_time_safe = html.escape(stage_time)
        stage_block = (
            f"\n📍 ЭТАП: {stage_name} ({stage_time_safe})\n"
            f"⚙️ УСТАВКИ: {current_v_set:.2f}В | {current_i_set:.2f}А"
        )
        
        if transition_condition:
            stage_block += f"\n{transition_condition}"  # Уже содержит HTML entities (&lt;, &gt;)
    
    # 4. ЧЕТВЕРТАЯ СТРОКА (Емкость)
    capacity_line = f"🔋 ЕМКОСТЬ: {ah:.2f} Ач"
    
    # Формируем итоговый текст (все переменные уже экранированы)
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
        sent = await bot.send_photo(chat_id, photo=photo, caption=text, reply_markup=ikb, parse_mode=ParseMode.HTML)
    else:
        sent = await bot.send_message(chat_id, text, reply_markup=ikb, parse_mode=ParseMode.HTML)

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
    last_cleanup_time = 0.0
    
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
            
            # Очистка базы данных каждые 24 часа (записи старше 7 дней)
            if now_ts - last_cleanup_time >= 86400:  # 24 часа
                await cleanup_old_records()
                last_cleanup_time = now_ts

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


async def get_ai_context() -> str:
    """Получить полный слепок данных RD6018 для AI анализа."""
    try:
        live = await hass.get_all_live()
        
        # Электрические параметры
        v_out = _safe_float(live.get("voltage", 0.0))
        i_out = _safe_float(live.get("current", 0.0))
        p_out = _safe_float(live.get("power", 0.0))
        v_batt = _safe_float(live.get("battery_voltage", 0.0))
        
        # Счетчики
        ah = _safe_float(live.get("ah", 0.0))
        wh = _safe_float(live.get("wh", 0.0))
        
        # Уставки
        v_set = _safe_float(live.get("set_voltage", 0.0))
        i_set = _safe_float(live.get("set_current", 0.0))
        ovp = _safe_float(live.get("ovp", 0.0))
        ocp = _safe_float(live.get("ocp", 0.0))
        
        # Статусы
        output_on = str(live.get("switch", "")).lower() == "on"
        cv_mode = str(live.get("is_cv", "")).lower() == "on"
        cc_mode = str(live.get("is_cc", "")).lower() == "on"
        battery_mode = not output_on  # Режим батареи = выход выключен
        
        # Температуры
        t_internal = _safe_float(live.get("temp_int", 0.0))
        t_external = _safe_float(live.get("temp_ext", 0.0))
        
        # Системные параметры (если доступны в HA)
        v_input = _safe_float(live.get("input_voltage", 0.0)) or 0.0  # Может отсутствовать
        uptime = live.get("uptime", "неизвестно")
        
        # Данные контроллера заряда
        controller_info = ""
        if charge_controller.is_active:
            timers = charge_controller.get_timers()
            controller_info = f"""
Контроллер заряда:
- Активный этап: {charge_controller.current_stage}
- Тип АКБ: {charge_controller.battery_type}
- Заданная емкость: {charge_controller.ah_capacity}Ач
- Общее время: {timers['total_time']}
- Время этапа: {timers['stage_time']}
- Лимит этапа: {timers['remaining_time']}"""
        
        # Формируем полный контекст
        context = f"""ПОЛНЫЙ СЛЕПОК RD6018:

Электрика:
- V_out: {v_out:.3f}В (напряжение на выходе)
- I_out: {i_out:.3f}А (ток нагрузки)
- P_out: {p_out:.2f}Вт (мощность)
- V_batt: {v_batt:.3f}В (напряжение на клеммах АКБ)

Счетчики:
- Ah: {ah:.3f} Ач (накопленная емкость)
- Wh: {wh:.2f} Вч (накопленная энергия)

Уставки:
- V_set: {v_set:.2f}В (целевое напряжение)
- I_set: {i_set:.2f}А (лимит тока)
- OVP: {ovp:.1f}В (защита перенапряжения)
- OCP: {ocp:.1f}А (защита перетока)

Статусы:
- Output_on: {output_on} (выход включен/выключен)
- CV_mode: {cv_mode} (режим стабилизации напряжения)
- CC_mode: {cc_mode} (режим стабилизации тока)
- Battery_mode: {battery_mode} (режим измерения АКБ)

Температура:
- T_internal: {t_internal:.1f}°C (температура блока)
- T_external: {t_external:.1f}°C (температура АКБ)

Система:
- V_input: {v_input:.1f}В (входное напряжение БП)
- Uptime: {uptime}{controller_info}"""
        
        # Последние события из лога
        from charging_log import get_recent_events
        recent_events = get_recent_events(5)
        if recent_events:
            context += "\n\nПоследние события:\n"
            for event in recent_events:
                context += f"- {event}\n"
        
        return context
    except Exception as ex:
        return f"Ошибка получения AI контекста: {ex}"


async def get_current_context_for_llm() -> str:
    """v2.6 Получить расширенный контекст для LLM: таймеры, параметры RD6018, события."""
    # Используем новую функцию для обратной совместимости
    return await get_ai_context()


@router.message(F.text)
async def text_message_handler(message: Message) -> None:
    """v2.6 Обработка текстовых сообщений: ввод ёмкости АКБ, ручной режим или режим диалога с LLM."""
    global awaiting_ah, custom_mode_state, last_chat_id, last_checkpoint_time
    user_id = message.from_user.id if message.from_user else 0
    
    # Проверяем ручной режим
    if user_id in custom_mode_state:
        await handle_custom_mode_input(message, user_id)
        return
    
    # Если ожидаем ввод ёмкости АКБ
    profile = awaiting_ah.get(user_id)
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
        # Получаем полный слепок данных RD6018
        context = await get_ai_context()
        
        # Системный промпт для эксперта-аккумуляторщика с полным контекстом
        system_prompt = """Ты — эксперт по свинцово-кислотным аккумуляторам и системам заряда RD6018.

Тебе доступны следующие живые данные прибора RD6018:
- Электрика: V_out, I_out, P_out, V_batt (на клеммах).
- Счетчики: Ah (емкость), Wh (энергия).
- Уставки: V_set, I_set, OVP, OCP.
- Статусы: Output_on (bool), CV_mode (bool), CC_mode (bool), Battery_mode (bool).
- Температура: T_internal (блок), T_external (АКБ).
- Система: V_input (входное БП), Uptime.

ТВОЯ ЛОГИКА АНАЛИЗА:
1. Если CV_mode = True, значит мы на 'полке' напряжения, и ток должен падать. Если он не падает — сигнализируй о возможном нагреве.
2. Если V_batt значительно ниже V_out — есть потери на проводах.
3. Если T_external быстро растет при низком токе — подозрение на КЗ банки.
4. Если V_input проседает ниже 60В при нагрузке — блок питания не тянет.

Отвечай как опытный аккумуляторщик, поясняй текущие процессы, диагностируй проблемы.
Используй HTML разметку: <b>жирный</b>, <i>курсив</i>, <code>моноширинный</code>.
Отвечай кратко и по существу на русском языке."""
        
        user_prompt = f"""=== ПОЛНЫЙ СЛЕПОК RD6018 ===
{context}

=== ВОПРОС ПОЛЬЗОВАТЕЛЯ ===
{user_question}

=== ЗАДАЧА ===
Проанализируй все доступные данные RD6018 и дай экспертное заключение с учетом:
- Текущего режима работы (CC/CV/Battery)
- Соответствия параметров нормальному процессу заряда
- Возможных проблем или аномалий
- Рекомендаций по оптимизации процесса"""

        # Асинхронный вызов LLM через executor для неблокирующей работы
        ai_response = await asyncio.get_event_loop().run_in_executor(
            executor, _call_deepseek_sync, system_prompt, user_prompt
        )
        
        if ai_response.startswith("ERROR:"):
            await thinking_msg.edit_text(f"🤖 {ai_response}")
        else:
            await thinking_msg.edit_text(
                f"🤖 <b>AI-Консультант:</b>\n\n{ai_response}",
                parse_mode=ParseMode.HTML
            )
                
    except Exception as ex:
        logger.error("handle_dialog_mode: %s", ex)
        await thinking_msg.edit_text("🤖 Ошибка при обращении к AI-консультанту.")


async def handle_custom_mode_input(message: Message, user_id: int) -> None:
    """Обработка ввода параметров в ручном режиме."""
    global custom_mode_state, custom_mode_data
    
    state = custom_mode_state.get(user_id)
    if not state:
        return
    
    text = (message.text or "").strip()
    if not text:
        await message.answer("❌ Пустое значение. Попробуйте еще раз.")
        return
    
    # Кнопка отмены для всех этапов
    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="custom_cancel")]]
    )
    
    try:
        value = float(text.replace(",", "."))
    except ValueError:
        await message.answer("❌ Некорректное число. Введите значение заново:", reply_markup=cancel_kb)
        return
    
    # Валидация в зависимости от этапа
    if state == "voltage":
        if value > 17.0 or value < 12.0:
            await message.answer(
                "⚠️ Опасно! Значение слишком высокое или низкое.\n"
                "Введите напряжение Main (12.0 - 17.0В):",
                reply_markup=cancel_kb
            )
            return
        custom_mode_data[user_id]["main_voltage"] = value
        custom_mode_state[user_id] = "current"
        custom_mode_confirm.pop(user_id, None)  # Очищаем подтверждение при переходе
        await message.answer(
            f"✅ Main: {value:.1f}В\n\n"
            "**Шаг 2/5:** Введите лимит тока Main (например 5.0):\n"
            "_Диапазон: 0.1 - 18.0А_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=cancel_kb
        )
    
    elif state == "current":
        # Проверка критических значений
        if value > 18.0:
            await message.answer(
                "🚫 ОШИБКА: RD6018 не поддерживает ток выше 18А. Введите корректное значение.",
                reply_markup=cancel_kb
            )
            return
        elif value < 0.1:
            await message.answer(
                "⚠️ Слишком низкое значение. Введите лимит тока Main (0.1 - 18.0А):",
                reply_markup=cancel_kb
            )
            return
        
        # Проверка опасных значений (10.1 - 18.0А)
        elif value > 10.0:
            # Проверяем, не подтверждение ли это
            confirm_data = custom_mode_confirm.get(user_id, {})
            if confirm_data.get("step") == "current" and abs(confirm_data.get("value", 0) - value) < 0.01:
                # Подтверждение получено - принимаем опасное значение
                custom_mode_data[user_id]["main_current"] = value
                custom_mode_state[user_id] = "delta"
                custom_mode_confirm.pop(user_id, None)  # Очищаем подтверждение
                
                await message.answer(
                    f"⚠️ ПРИНЯТО: {custom_mode_data[user_id]['main_voltage']:.1f}В / {value:.1f}А\n\n"
                    "**Шаг 3/5:** Введите дельту (0.01 - 0.05):\n"
                    "_Чем меньше, тем чувствительнее финиш. Стандарт: 0.03_",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=cancel_kb
                )
            else:
                # Первый ввод опасного значения - требуем подтверждения
                custom_mode_confirm[user_id] = {"step": "current", "value": value}
                await message.answer(
                    f"⚠️ ВНИМАНИЕ: Ток {value:.1f}А выше 10А опасен для большинства АКБ и может перегреть RD6018.\n\n"
                    "Вы уверены? Введите ток еще раз для подтверждения или введите значение до 10А.",
                    reply_markup=cancel_kb
                )
            return
        
        # Безопасное значение (0.1 - 10.0А)
        else:
            custom_mode_data[user_id]["main_current"] = value
            custom_mode_state[user_id] = "delta"
            custom_mode_confirm.pop(user_id, None)  # Очищаем подтверждение если было
            
            await message.answer(
                f"✅ Main: {custom_mode_data[user_id]['main_voltage']:.1f}В / {value:.1f}А\n\n"
                "**Шаг 3/5:** Введите дельту (0.01 - 0.05):\n"
                "_Чем меньше, тем чувствительнее финиш. Стандарт: 0.03_",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=cancel_kb
            )
    
    elif state == "delta":
        if value < 0.005 or value > 0.1:
            await message.answer(
                "⚠️ Значение вне допустимого диапазона!\n"
                "Введите дельту (0.005 - 0.1В). Рекомендуется: 0.03В",
                reply_markup=cancel_kb
            )
            return
        custom_mode_data[user_id]["delta"] = value
        custom_mode_state[user_id] = "time_limit"
        custom_mode_confirm.pop(user_id, None)  # Очищаем подтверждение при переходе
        await message.answer(
            f"✅ Delta: {value:.3f}В\n\n"
            "**Шаг 4/5:** Введите лимит времени в часах (например 24):\n"
            "_Диапазон: 1 - 72ч. Заряд без присмотра запрещен!_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=cancel_kb
        )
    
    elif state == "time_limit":
        if value <= 0 or value > 72:
            await message.answer(
                "⚠️ БЕЗОПАСНОСТЬ: Оставлять заряд без присмотра категорически запрещено.\n"
                "Введите лимит от 1 до 72 часов:",
                reply_markup=cancel_kb
            )
            return
        
        custom_mode_data[user_id]["time_limit"] = value
        custom_mode_state[user_id] = "capacity"
        custom_mode_confirm.pop(user_id, None)  # Очищаем подтверждение при переходе
        await message.answer(
            f"✅ Лимит: {value:.0f}ч\n\n"
            "**Шаг 5/5:** Введите ёмкость АКБ в Ah (например 60):\n"
            "_Диапазон: 10 - 300 Ah_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=cancel_kb
        )
    
    elif state == "capacity":
        if value < 10 or value > 300:
            await message.answer(
                "⚠️ Значение вне допустимого диапазона!\n"
                "Введите ёмкость АКБ (10 - 300 Ah):",
                reply_markup=cancel_kb
            )
            return
        
        # Завершаем настройку
        custom_mode_data[user_id]["capacity"] = value
        data = custom_mode_data[user_id]
        
        # Очищаем состояние FSM
        del custom_mode_state[user_id]
        del custom_mode_data[user_id]
        custom_mode_confirm.pop(user_id, None)  # Очищаем подтверждение если было
        
        # Запускаем заряд
        await start_custom_charge(message, user_id, data)


async def start_custom_charge(message: Message, user_id: int, params: Dict[str, float]) -> None:
    """Запуск заряда в ручном режиме."""
    global last_chat_id, last_checkpoint_time
    last_chat_id = message.chat.id
    
    try:
        # Получаем текущие данные
        live = await hass.get_all_live()
        battery_v = _safe_float(live.get("battery_voltage", 12.0))
        i = _safe_float(live.get("current", 0.0))
        t = _safe_float(live.get("temp_ext", 25.0))
        ah_val = _safe_float(live.get("ah", 0.0))
        
        # Запускаем контроллер в ручном режиме
        charge_controller.start_custom(
            main_voltage=params["main_voltage"],
            main_current=params["main_current"],
            delta_threshold=params["delta"],
            time_limit_hours=params["time_limit"],
            ah_capacity=int(params["capacity"])
        )
        
        # Устанавливаем параметры на RD6018
        await hass.set_voltage(params["main_voltage"])
        await hass.set_current(params["main_current"])
        await hass.turn_on(ENTITY_MAP["switch"])
        
        last_checkpoint_time = time.time()
        log_event("Подготовка", battery_v, i, t, ah_val, 
                 f"START CUSTOM main={params['main_voltage']:.1f}V/{params['main_current']:.1f}A "
                 f"delta={params['delta']:.3f}V limit={params['time_limit']:.0f}h ah={params['capacity']:.0f}")
        
        # Показываем результат
        summary = (
            f"✅ **Ручной режим запущен!**\n\n"
            f"📋 **Параметры:**\n"
            f"• Main: {params['main_voltage']:.1f}В / {params['main_current']:.1f}А\n"
            f"• Delta: {params['delta']:.3f}В\n"
            f"• Лимит: {params['time_limit']:.0f}ч\n"
            f"• Емкость: {params['capacity']:.0f} Ah\n\n"
            f"🔋 **АКБ:** {battery_v:.2f}В | {i:.2f}А"
        )
        
        await message.answer(summary, parse_mode=ParseMode.MARKDOWN)
        
        # Обновляем дашборд
        old_id = user_dashboard.get(user_id)
        await send_dashboard(message, old_msg_id=old_id)
        
    except Exception as ex:
        logger.error("start_custom_charge error: %s", ex)
        await message.answer("❌ Ошибка запуска ручного режима. Проверьте подключение к RD6018.")


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
            [InlineKeyboardButton(text="🛠 Ручной режим", callback_data="profile_custom")],
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


@router.callback_query(F.data == "custom_cancel")
async def custom_mode_cancel(call: CallbackQuery) -> None:
    """Отменить ручной режим и вернуться в главное меню."""
    try:
        await call.answer("Ручной режим отменен")
    except Exception:
        pass
    
    global custom_mode_state, custom_mode_data, custom_mode_confirm
    user_id = call.from_user.id if call.from_user else 0
    
    # Очищаем состояние FSM
    if user_id in custom_mode_state:
        del custom_mode_state[user_id]
    if user_id in custom_mode_data:
        del custom_mode_data[user_id]
    if user_id in custom_mode_confirm:
        del custom_mode_confirm[user_id]
    
    # Возвращаемся в главное меню
    old_id = user_dashboard.get(call.from_user.id) if call.from_user else None
    await send_dashboard(call, old_msg_id=old_id)


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


@router.callback_query(F.data == "profile_custom")
async def custom_mode_start(call: CallbackQuery) -> None:
    """Начать ручной режим с приветственным сообщением."""
    try:
        await call.answer()
    except Exception:
        pass
    
    global custom_mode_state, custom_mode_data, last_chat_id
    last_chat_id = call.message.chat.id
    user_id = call.from_user.id if call.from_user else 0
    
    # Инициализируем состояние
    custom_mode_state[user_id] = "voltage"
    custom_mode_data[user_id] = {}
    
    # Приветственное сообщение
    welcome_text = (
        "🛠 **Ручной режим (Custom)**\n\n"
        "• **Main:** До 80% емкости (обычно 14.7В).\n"
        "• **Mix:** Финальный дозаряд (16+ В).\n"
        "• **Delta:** Чувствительность финиша (0.03В — стандарт).\n"
        "• **Limit:** Защита по времени.\n\n"
        "⚠️ **ВНИМАНИЕ:** Высокие напряжения! Убедитесь, что АКБ отключена от бортсети."
    )
    
    # Кнопка отмены
    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="custom_cancel")]]
    )
    
    await call.message.answer(welcome_text, parse_mode=ParseMode.MARKDOWN, reply_markup=cancel_kb)
    
    # Начинаем ввод напряжения Main
    await call.message.answer(
        "**Шаг 1/5:** Введите напряжение Main (например 14.7):\n"
        "_Диапазон: 12.0 - 17.0В_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=cancel_kb
    )


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
    
    # Получаем реальные события из лога заряда
    from charging_log import get_recent_events
    try:
        recent_events = get_recent_events(15)  # Последние 15 событий
        if not recent_events:
            text = "<b>📝 Логи событий</b>\n\nНет событий."
        else:
            lines = ["<b>📝 Логи событий</b>\n"]
            for event in recent_events:
                # Парсим строку события для красивого форматирования
                formatted_event = format_log_event(event)
                if formatted_event.strip():  # Пропускаем пустые строки
                    lines.append(formatted_event)
            
            # Проверяем, что у нас есть события для отображения
            if len(lines) <= 1:
                text = "<b>📝 Логи событий</b>\n\nТолько служебные события."
            else:
                text = "\n".join(lines)
    except Exception as ex:
        logger.error("Failed to get recent events: %s", ex)
        text = "<b>📝 Логи событий</b>\n\n❌ Ошибка загрузки событий."
    
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