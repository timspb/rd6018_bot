"""
bot.py — RD6018 Ultimate Telegram Controller (Async Edition).
Дашборд: один автообновляемый message с графиком, метриками и кнопками.
"""
import asyncio
import json
import logging
import os
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
from ai_system_prompt import AI_CONSULTANT_SYSTEM_PROMPT
from charge_logic import (
    ChargeController,
    DELTA_I_EXIT,
    DELTA_V_EXIT,
    HIGH_V_FAST_TIMEOUT,
    HIGH_V_THRESHOLD,
    WATCHDOG_TIMEOUT,
    OVP_OFFSET,
    OCP_OFFSET,
)
from charging_log import clear_event_logs, log_checkpoint, log_event, log_stage_end, rotate_if_needed, trim_log_older_than_days
from config import (
    ALLOWED_CHAT_IDS,
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    ENTITY_MAP,
    HA_URL,
    HA_TOKEN,
    MIN_INPUT_VOLTAGE,
    TEMP_INT_PRECRITICAL,
    TG_TOKEN,
)
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


def _charge_notify(msg: str, critical: bool = True) -> None:
    """Отправка уведомления в Telegram. critical=True — после него дашборд только по кнопке ОБНОВИТЬ; critical=False — сразу шлём дашборд последним сообщением."""
    global last_chat_id
    if last_chat_id and msg:
        asyncio.create_task(_send_notify_safe(msg, critical))


async def _send_notify_safe(msg: str, critical: bool = True) -> None:
    global last_chat_id, last_user_id
    try:
        safe_msg = msg
        if not any(tag in msg for tag in ['<b>', '<i>', '<code>']):
            safe_msg = html.escape(msg)
        safe_msg = safe_msg.replace('<hr>', '___________________').replace('<hr/>', '___________________').replace('<hr />', '___________________')
        safe_msg = safe_msg.replace('<br>', '\n').replace('<br/>', '\n').replace('<br />', '\n')
        await bot.send_message(last_chat_id, safe_msg, parse_mode=ParseMode.HTML)
        if not critical and last_chat_id:
            await send_dashboard_to_chat(last_chat_id, last_user_id or 0)
    except Exception as ex:
        logger.error("charge notify failed: %s", ex)
        try:
            clean_msg = html.escape(msg).replace('<hr>', '---').replace('<hr/>', '---').replace('<hr />', '---')
            await bot.send_message(last_chat_id, clean_msg)
            if not critical and last_chat_id:
                await send_dashboard_to_chat(last_chat_id, last_user_id or 0)
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


def _is_chat_allowed(chat_id: int) -> bool:
    """Проверка доступа по ALLOWED_CHAT_IDS. Пустой список = доступ у всех."""
    if not ALLOWED_CHAT_IDS:
        return True
    return chat_id in ALLOWED_CHAT_IDS


async def _check_chat_and_respond(event: Union[Message, CallbackQuery]) -> bool:
    """
    Вернуть True, если чат разрешён. Иначе отправить «Доступ запрещён» и вернуть False.
    Вызывать в начале обработчиков.
    """
    chat_id = event.chat.id if isinstance(event, Message) else event.message.chat.id
    if _is_chat_allowed(chat_id):
        return True
    try:
        if isinstance(event, Message):
            await event.answer("Доступ запрещён.")
        else:
            await event.answer("Доступ запрещён.", show_alert=True)
    except Exception:
        pass
    return False


user_dashboard: Dict[int, int] = {}
last_chat_id: Optional[int] = None
last_user_id: Optional[int] = None
last_charge_alert_at: Optional[datetime] = None
last_idle_alert_at: Optional[datetime] = None
zero_current_since: Optional[datetime] = None
CHARGE_ALERT_COOLDOWN = timedelta(hours=1)
# В режиме хранения (V < 14В) алерт «заряд завершён» не чаще раза в час
STORAGE_ALERT_COOLDOWN = timedelta(hours=1)
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
MIN_START_TEMP = 10.0  # °C — заряд не начинаем, если внешний датчик ниже
last_checkpoint_time: float = 0.0

# Команда off: выключить по напряжению / току / таймеру (игнорируя режим, защита остаётся)
manual_off_voltage: Optional[float] = None    # выкл когда V >=
manual_off_voltage_le: Optional[float] = None  # выкл когда V <= (напр. спад в миксе)
manual_off_current: Optional[float] = None     # выкл когда I <=
manual_off_current_ge: Optional[float] = None  # выкл когда I >= (напр. рост от 1 А к 2 А)
manual_off_time_sec: Optional[float] = None
manual_off_start_time: float = 0.0

MANUAL_OFF_FILE = "manual_off_state.json"


def _save_manual_off_state() -> None:
    """Сохранить условие «off» в файл (переживёт перезапуск бота)."""
    if not _has_manual_off_condition():
        try:
            if os.path.exists(MANUAL_OFF_FILE):
                os.remove(MANUAL_OFF_FILE)
        except OSError:
            pass
        return
    data = {
        "voltage_ge": manual_off_voltage,
        "voltage_le": manual_off_voltage_le,
        "current_le": manual_off_current,
        "current_ge": manual_off_current_ge,
        "time_sec": manual_off_time_sec,
        "start_time": manual_off_start_time,
    }
    try:
        with open(MANUAL_OFF_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError as ex:
        logger.warning("Could not save manual_off state: %s", ex)


def _load_manual_off_state() -> None:
    """Восстановить условие «off» из файла после перезапуска бота."""
    global manual_off_voltage, manual_off_voltage_le, manual_off_current, manual_off_current_ge, manual_off_time_sec, manual_off_start_time
    if not os.path.exists(MANUAL_OFF_FILE):
        return
    try:
        with open(MANUAL_OFF_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return
    v_ge = data.get("voltage_ge")
    v_le = data.get("voltage_le")
    i_le = data.get("current_le")
    i_ge = data.get("current_ge")
    t_sec = data.get("time_sec")
    start = data.get("start_time")
    if v_ge is None and v_le is None and i_le is None and i_ge is None and t_sec is None:
        return
    manual_off_voltage = float(v_ge) if v_ge is not None else None
    manual_off_voltage_le = float(v_le) if v_le is not None else None
    manual_off_current = float(i_le) if i_le is not None else None
    manual_off_current_ge = float(i_ge) if i_ge is not None else None
    manual_off_time_sec = float(t_sec) if t_sec is not None else None
    try:
        manual_off_start_time = float(start) if start is not None else 0.0
    except (TypeError, ValueError):
        manual_off_start_time = 0.0
    logger.info("Manual off condition restored from %s", MANUAL_OFF_FILE)


def _parse_off_command(text: str) -> Optional[Dict[str, Any]]:
    """
    Парсит команду off с явными условиями:
    V>=16.4 / V<=13.2 — по напряжению (достигнет ≥ или снизится до ≤);
    I<=1.23 / I>=2 — по току (достигнет ≤ или достигнет ≥);
    2:23 — таймер.
    Без префикса: число 12–18 В → V>=, 0.1–18 А → I<= (как раньше).
    """
    t = (text or "").strip().replace(",", ".")
    if not t.lower().startswith("off "):
        return None
    rest = t[4:].strip().replace("\u2265", ">=").replace("\u2264", "<=")  # ≥ ≤
    if not rest:
        return None
    tokens = rest.lower().split()
    voltage_ge: Optional[float] = None
    voltage_le: Optional[float] = None
    current_le: Optional[float] = None
    current_ge: Optional[float] = None
    time_sec: Optional[float] = None
    parts: list = []

    for tok in tokens:
        if ":" in tok:
            try:
                comp = tok.split(":")
                if len(comp) == 2:
                    h, m = int(comp[0].strip()), int(comp[1].strip())
                    sec = h * 3600 + m * 60
                elif len(comp) == 3:
                    h, m, s = int(comp[0].strip()), int(comp[1].strip()), int(comp[2].strip())
                    sec = h * 3600 + m * 60 + s
                else:
                    continue
                if sec <= 0:
                    continue
                time_sec = (time_sec or 0) + sec
                parts.append(f"таймер {tok}")
            except (ValueError, IndexError):
                continue
        elif tok.startswith("v>="):
            try:
                voltage_ge = float(tok[3:].strip())
                if 0 <= voltage_ge <= 20:
                    parts.append(f"V≥{voltage_ge:.1f} В")
            except ValueError:
                continue
        elif tok.startswith("v<="):
            try:
                voltage_le = float(tok[3:].strip())
                if 0 <= voltage_le <= 20:
                    parts.append(f"V≤{voltage_le:.1f} В")
            except ValueError:
                continue
        elif tok.startswith("i>="):
            try:
                current_ge = float(tok[3:].strip())
                if 0 < current_ge <= 18:
                    parts.append(f"I≥{current_ge:.2f} А")
            except ValueError:
                continue
        elif tok.startswith("i<="):
            try:
                current_le = float(tok[3:].strip())
                if 0 < current_le <= 18:
                    parts.append(f"I≤{current_le:.2f} А")
            except ValueError:
                continue
        else:
            try:
                val = float(tok)
                if 12.0 <= val <= 18.0:
                    voltage_ge = val
                    parts.append(f"{val:.1f} В (V≥)")
                elif 0.1 <= val <= 18.0:
                    current_le = val
                    parts.append(f"{val:.2f} А (I≤)")
                else:
                    continue
            except ValueError:
                continue

    if voltage_ge is None and voltage_le is None and current_le is None and current_ge is None and time_sec is None:
        return None
    return {
        "voltage_ge": voltage_ge,
        "voltage_le": voltage_le,
        "current_le": current_le,
        "current_ge": current_ge,
        "time_sec": time_sec,
        "start_time": time.time(),
        "parts": parts,
    }


def _clear_manual_off() -> None:
    global manual_off_voltage, manual_off_voltage_le, manual_off_current, manual_off_current_ge, manual_off_time_sec, manual_off_start_time
    manual_off_voltage = None
    manual_off_voltage_le = None
    manual_off_current = None
    manual_off_current_ge = None
    manual_off_time_sec = None
    manual_off_start_time = 0.0
    _save_manual_off_state()


def _has_manual_off_condition() -> bool:
    return (
        manual_off_voltage is not None or manual_off_voltage_le is not None
        or manual_off_current is not None or manual_off_current_ge is not None
        or manual_off_time_sec is not None
    )


def _format_manual_off_for_dashboard() -> str:
    """Строка для дашборда: статус принудительного выключения и остаток времени до выкл."""
    global manual_off_voltage, manual_off_voltage_le, manual_off_current, manual_off_current_ge, manual_off_time_sec, manual_off_start_time
    if not _has_manual_off_condition():
        return ""
    parts = []
    # «Достигли» V: оба порога равны
    if (
        manual_off_voltage is not None
        and manual_off_voltage_le is not None
        and abs(manual_off_voltage - manual_off_voltage_le) < 0.01
    ):
        parts.append(f"при достижении V {manual_off_voltage:.2f} В")
    else:
        if manual_off_voltage is not None:
            parts.append(f"при V≥{manual_off_voltage:.1f} В")
        if manual_off_voltage_le is not None:
            parts.append(f"при V≤{manual_off_voltage_le:.1f} В")
    # «Достигли» I: оба порога равны
    if (
        manual_off_current is not None
        and manual_off_current_ge is not None
        and abs(manual_off_current - manual_off_current_ge) < 0.01
    ):
        parts.append(f"при достижении I {manual_off_current:.2f} А")
    else:
        if manual_off_current is not None:
            parts.append(f"при I≤{manual_off_current:.2f} А")
        if manual_off_current_ge is not None:
            parts.append(f"при I≥{manual_off_current_ge:.2f} А")
    remaining_sec = 0.0
    if manual_off_time_sec is not None:
        remaining_sec = manual_off_start_time + manual_off_time_sec - time.time()
        if remaining_sec <= 0:
            parts.append("таймер истёк")
        else:
            h = int(manual_off_time_sec // 3600)
            m = int((manual_off_time_sec % 3600) // 60)
            parts.append(f"таймер {h}:{m:02d}")
    line = "⏹ ВЫКЛ ПО УСЛОВИЮ: " + ", ".join(parts)
    if manual_off_time_sec is not None and remaining_sec > 0:
        h = int(remaining_sec // 3600)
        m = int((remaining_sec % 3600) // 60)
        line += f" | осталось до выкл: {h}:{m:02d}"
    return line


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


def _parse_uptime_to_elapsed_sec(uptime_raw) -> Optional[float]:
    """
    Преобразует uptime из HA в прошедшие секунды.
    Поддерживает: число (секунды), строку "8:36" (H:MM) или "8:36:00" (H:MM:SS), ISO-дату.
    """
    if uptime_raw is None or uptime_raw == "":
        return None
    if isinstance(uptime_raw, (int, float)):
        return float(uptime_raw)
    s = str(uptime_raw).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        pass
    # Формат таймера прибора: "8:36" (ч:мин), "8:36:00" (ч:мин:сек), "9:00" (минуты:секунды при < 1 ч)
    if ":" in s and "T" not in s and "-" not in s:
        parts = s.split(":")
        try:
            if len(parts) == 2:
                a, b = int(parts[0].strip()), int(parts[1].strip())
                if a == 0:
                    return b * 60  # "0:09" = 0 ч 9 мин
                if 1 <= a <= 59 and b == 0:
                    return a * 60  # "9:00" = 9 мин (таймер прибора часто MM:SS при < 1 ч)
                return a * 3600 + b * 60  # часы:минуты "8:36"
            if len(parts) == 3:
                h, m, sec = int(parts[0].strip()), int(parts[1].strip()), int(parts[2].strip())
                return h * 3600 + m * 60 + sec
        except (ValueError, IndexError):
            pass
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        elapsed = time.time() - dt.timestamp()
        if elapsed < 0:
            return None  # дата в будущем — не использовать
        return elapsed
    except Exception:
        return None


# Макс. время (сек), при котором считаем uptime таймером заряда (иначе — время с включения прибора)
UPTIME_AS_CHARGE_TIMER_MAX_SEC = 24 * 3600


def _format_uptime_display(uptime_raw) -> str:
    """
    Форматирование сущности sensor.rd_6018_uptime для отображения.
    Если приходит ISO-дата (момент старта заряда) — показываем «Старт: DD.MM HH:MM (прошло ЧЧ:ММ)».
    Иначе — сырое значение (число секунд или строка типа "8:36").
    """
    if uptime_raw is None or uptime_raw == "":
        return "—"
    s = str(uptime_raw).strip()
    if not s:
        return "—"
    # ISO datetime: 2026-02-12T14:38:56+00:00 — момент старта заряда
    if "T" in s and "-" in s:
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            start_str = dt.strftime("%d.%m.%Y %H:%M")
            elapsed = _parse_uptime_to_elapsed_sec(uptime_raw)
            if elapsed is not None and 0 <= elapsed <= UPTIME_AS_CHARGE_TIMER_MAX_SEC:
                h, m = int(elapsed // 3600), int((elapsed % 3600) // 60)
                return f"Старт: {start_str} (прошло {h:02d}:{m:02d})"
            return f"Старт: {start_str}"
        except Exception:
            return s
    # Число или строка "8:36"
    elapsed = _parse_uptime_to_elapsed_sec(uptime_raw)
    if elapsed is not None and 0 <= elapsed <= UPTIME_AS_CHARGE_TIMER_MAX_SEC:
        h, m = int(elapsed // 3600), int((elapsed % 3600) // 60)
        return f"{h:02d}:{m:02d}"
    return s


def _apply_restore_time_corrections(charge_controller, live: Optional[Dict]) -> None:
    """
    После восстановления: пауза потери связи вычитается из таймеров.
    Если sensor.rd_6018_uptime возвращает таймер заряда (как на дисплее, ≤24ч) — синхронизируем общее время.
    """
    now = time.time()
    link_lost = getattr(charge_controller, "_link_lost_at", 0) or 0
    if link_lost > 0:
        gap = now - link_lost
        charge_controller.total_start_time += gap
        charge_controller.stage_start_time += gap
        charge_controller._link_lost_at = 0
    uptime_raw = (live or {}).get("uptime")
    elapsed = _parse_uptime_to_elapsed_sec(uptime_raw)
    if elapsed is not None and 0 < elapsed <= UPTIME_AS_CHARGE_TIMER_MAX_SEC:
        charge_controller.total_start_time = now - elapsed


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
    
    # Заменяем неподдерживаемые HTML теги на текстовые аналоги
    result = template.format(**safe_kwargs)
    result = result.replace('<hr>', '___________________')
    result = result.replace('<hr/>', '___________________')
    result = result.replace('<hr />', '___________________')
    
    return result


# Глобальные переменные для отслеживания RESTORE событий
_last_restore_time: float = 0.0
_script_start_time: float = time.time()

def _remove_duplicate_events(events: list) -> list:
    """Удаляет дубли идущих подряд событий, группирует RESTORE с счетчиком."""
    if not events:
        return events
    
    filtered_events = []
    prev_event_type = None
    restore_count = 0
    last_restore_event = None
    
    for event in events:
        # Извлекаем тип события (например, "RESTORE", "START", "MAIN", etc.)
        event_parts = event.split(' | ')
        if len(event_parts) > 6:
            current_event_type = event_parts[6].strip().split()[0] if event_parts[6].strip() else ""
            stage = event_parts[1].strip()
            
            # Специальная обработка RESTORE событий
            if current_event_type == "RESTORE":
                if prev_event_type == f"{stage}_RESTORE":
                    # Увеличиваем счетчик RESTORE
                    restore_count += 1
                    last_restore_event = event
                else:
                    # Добавляем предыдущий RESTORE с счетчиком если был
                    if last_restore_event and restore_count > 1:
                        # Модифицируем событие добавляя счетчик
                        parts = last_restore_event.split(' | ')
                        if len(parts) > 6:
                            parts[6] = f"RESTORE (x{restore_count})"
                            filtered_events.append(' | '.join(parts))
                    elif last_restore_event:
                        filtered_events.append(last_restore_event)
                    
                    # Начинаем новую группу RESTORE
                    restore_count = 1
                    last_restore_event = event
                    prev_event_type = f"{stage}_RESTORE"
                continue
            else:
                # Завершаем группу RESTORE если была
                if last_restore_event:
                    if restore_count > 1:
                        parts = last_restore_event.split(' | ')
                        if len(parts) > 6:
                            parts[6] = f"RESTORE (x{restore_count})"
                            filtered_events.append(' | '.join(parts))
                    else:
                        filtered_events.append(last_restore_event)
                    last_restore_event = None
                    restore_count = 0
            
            # Создаем ключ для группировки (тип события + этап)
            event_key = f"{stage}_{current_event_type}"
            
            # Если это не дубль или это важное событие, добавляем
            if (event_key != prev_event_type or 
                current_event_type in ["START", "DONE", "EMERGENCY", "STOP"]):
                filtered_events.append(event)
                prev_event_type = event_key
            else:
                # Заменяем предыдущее событие того же типа на текущее (более новое)
                if filtered_events:
                    filtered_events[-1] = event
        else:
            # Если формат события неожиданный, добавляем как есть
            filtered_events.append(event)
            prev_event_type = None
    
    # Добавляем последний RESTORE если был
    if last_restore_event:
        if restore_count > 1:
            parts = last_restore_event.split(' | ')
            if len(parts) > 6:
                parts[6] = f"RESTORE (x{restore_count})"
                filtered_events.append(' | '.join(parts))
        else:
            filtered_events.append(last_restore_event)
    
    return filtered_events


def _should_hide_restore_event(event: str) -> bool:
    """Определяет, нужно ли скрыть RESTORE событие от пользователя."""
    global _last_restore_time, _script_start_time
    
    if "RESTORE" not in event:
        return False
    
    current_time = time.time()
    
    # Показываем RESTORE только если:
    # 1. Это первый RESTORE после запуска скрипта (в течение первых 5 минут)
    # 2. Прошло более 2 минут с последнего показанного RESTORE
    if (current_time - _script_start_time < 300 and _last_restore_time == 0) or \
       (current_time - _last_restore_time > 120):
        _last_restore_time = current_time
        return False  # Показываем событие
    
    return True  # Скрываем событие


def format_log_event(event_line: str) -> str:
    """Форматирование строки события в красивый вид с иконками."""
    try:
        # Парсим строку формата: [2024-02-12 19:15:23] | Main Charge  | 14.80 | 2.40 | 25.1 |  60.25 | START | Емкость: 60Ah
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
        stage_short = stage.replace("Main Charge", "Main").replace("Десульфатация", "Desulf").replace("Безопасное ожидание", "Wait")
        stage_escaped = html.escape(stage_short)

        # Завершение этапа: END | Время: ... | Ёмкость: ... | T: ... | V: ... | I: ... | Триггер: ...
        if event.startswith("END |"):
            icon = "📊"
            text = f"[{time_only}] {icon} <b>{stage_escaped}: завершён</b>\n"
            rest = event[5:].strip()  # после "END |"
            # Парсим пары "Ключ: значение"
            for part in rest.split(" | "):
                part = part.strip()
                if ":" in part:
                    k, v = part.split(":", 1)
                    text += f"└ {k.strip()}: {v.strip()}\n"
            return text.rstrip()

        # Действие по триггеру в текущем этапе (вложенная строка)
        if event.strip().startswith("└"):
            detail = event.strip()[1:].strip()  # убираем └
            return f"[{time_only}] └ {html.escape(detail)}"

        # Старт этапа: START | Емкость: XAh [| profile=...]
        if "START" in event:
            icon = "🏁"
            text = f"[{time_only}] {icon} <b>{stage_escaped}: START</b>\n"
            if "Емкость:" in event:
                m = re.search(r"Емкость:\s*(\d+)\s*Ah", event, re.IGNORECASE)
                if m:
                    text += f"└ Емкость: {m.group(1)}Ah\n"
            if "profile=" in event:
                for p in ("EFB", "AGM", "Ca/Ca"):
                    if p in event:
                        text += f"└ Профиль: {p}\n"
                        break
            if "CUSTOM" in event and "profile=" not in event:
                text += "└ Профиль: Custom\n"
            return text.rstrip()

        # Остальные события (EMERGENCY, DONE, старый формат и т.д.)
        icon = "📋"
        if "DONE" in event or "FINISH" in event:
            icon = "✅"
        elif "STOP" in event or "EMERGENCY" in event:
            icon = "🛑"
        elif "WARNING" in event or "TEMP" in event:
            icon = "⚠️"
        elif "CHECKPOINT" in event:
            return ""
        elif "RESTORE" in event:
            return ""
        if _should_hide_restore_event(event):
            return ""
        event_escaped = html.escape(event)
        return f"[{time_only}] {icon} <b>{stage_escaped}</b>: {event_escaped}"
            
    except Exception as ex:
        logger.error("Failed to format log event: %s", ex)
        return f"<code>{html.escape(event_line[:100])}</code>"


def _build_dashboard_blocks(live: Dict[str, Any]) -> tuple:
    """
    Построить блоки текста дашборда по данным live.
    Возвращает (status_line, live_line, stage_block, capacity_line).
    """
    battery_v = _safe_float(live.get("battery_voltage"))
    set_v = _safe_float(live.get("set_voltage"))
    set_i = _safe_float(live.get("set_current"))
    is_on = str(live.get("switch", "")).lower() == "on"
    i = _safe_float(live.get("current"))
    temp_ext = _safe_float(live.get("temp_ext"))
    temp_int = _safe_float(live.get("temp_int"))
    ah = _safe_float(live.get("ah"))
    is_cv = str(live.get("is_cv", "")).lower() == "on"
    is_cc = str(live.get("is_cc", "")).lower() == "on"
    mode = "CV" if is_cv else ("CC" if is_cc else "-")
    output_v = _safe_float(live.get("voltage"))

    # Синхронизация таймера с прибором: при каждом построении дашборда подставляем время из сущности uptime
    if charge_controller.is_active and live.get("uptime") is not None:
        elapsed = _parse_uptime_to_elapsed_sec(live.get("uptime"))
        if elapsed is not None and 0 < elapsed <= UPTIME_AS_CHARGE_TIMER_MAX_SEC:
            charge_controller.total_start_time = time.time() - elapsed

    if charge_controller.is_active:
        timers = charge_controller.get_timers()
        status_emoji = "⚡️" if (is_on and i > 0.05) else "⏸️"
        stage_name = html.escape(charge_controller.current_stage)
        battery_type = html.escape(charge_controller.battery_type)
        total_time = html.escape(timers["total_time"])
        status_line = f"📊 СТАТУС: {status_emoji} {stage_name} | {battery_type} | ⏱ {total_time}"
    else:
        status_line = f"📊 СТАТУС: 💤 Ожидание | АКБ: {battery_v:.2f}В"
        if is_on and i > 0.05:
            status_line += f" | ⚠️ Выход вкл {i:.2f}А, бот не управляет"

    electrical_data = format_electrical_data(battery_v, i)
    temp_data = format_temperature_data(temp_ext, temp_int)
    live_line = f"⚡️ LIVE: {electrical_data} | {mode} | {temp_data}"

    stage_block = ""
    if charge_controller.is_active:
        timers = charge_controller.get_timers()
        stage_time = timers["stage_time"]
        current_v_set = _safe_float(live.get("set_voltage", set_v))
        current_i_set = _safe_float(live.get("set_current", set_i))
        transition_condition = ""
        raw_stage = charge_controller.current_stage
        time_limit = timers["remaining_time"]

        if "Main" in raw_stage:
            if charge_controller.battery_type == "Custom":
                transition_condition = "🔜 ФИНИШ: &lt;0.30А"
            elif charge_controller.battery_type in ["Ca/Ca", "EFB"]:
                transition_condition = "🔜 ПЕРЕХОД: &lt;0.30А"
            elif charge_controller.battery_type == "AGM":
                transition_condition = "🔜 ПЕРЕХОД: &lt;0.20А"
        elif "Mix" in raw_stage:
            v_max = charge_controller.v_max_recorded
            i_min = charge_controller.i_min_recorded
            if is_cv:
                if i_min is not None:
                    expect_i = i_min + DELTA_I_EXIT
                    transition_condition = f"🔜 ФИНИШ: ΔI +{DELTA_I_EXIT}А I≥{expect_i:.2f}А"
                else:
                    transition_condition = f"🔜 ФИНИШ: ΔI +{DELTA_I_EXIT}А"
            elif is_cc:
                if v_max is not None:
                    expect_v = v_max - DELTA_V_EXIT
                    transition_condition = f"🔜 ФИНИШ: ΔV −{DELTA_V_EXIT}В V≤{expect_v:.2f}В"
                else:
                    transition_condition = f"🔜 ФИНИШ: ΔV −{DELTA_V_EXIT}В"
            else:
                transition_condition = f"🔜 ФИНИШ: ΔV −{DELTA_V_EXIT}В (CC) или ΔI +{DELTA_I_EXIT}А (CV)"
        elif "Десульфатация" in raw_stage:
            transition_condition = "🔜 ПЕРЕХОД: 2ч"
        elif "Безопасное ожидание" in raw_stage:
            transition_condition = "🔜 ПЕРЕХОД: падение V"
        elif "Остывание" in raw_stage:
            transition_condition = "🔜 ВОЗВРАТ: T&le;35°C"

        if time_limit != "—":
            try:
                if ":" in time_limit:
                    hours = int(time_limit.split(":")[0])
                    time_display = f"{hours}ч" if hours > 0 else "менее 1ч"
                else:
                    time_display = time_limit
            except Exception:
                time_display = time_limit
            if transition_condition:
                transition_condition = f"{transition_condition} | ⏱ {time_display}"
            else:
                transition_condition = f"🔜 ⏱ {time_display}"

        stage_name = html.escape(charge_controller.current_stage)
        stage_time_safe = html.escape(stage_time)
        stage_block = (
            f"\n📍 ЭТАП: {stage_name} | ⏱ {stage_time_safe}\n"
            f"⚙️ УСТАВКИ: {current_v_set:.2f}В | {current_i_set:.2f}А\n"
            f"{transition_condition}"
        )

    capacity_line = f"🔋 ЕМКОСТЬ: {ah:.2f} Ач"
    return status_line, live_line, stage_block, capacity_line


async def _build_and_send_dashboard(chat_id: int, user_id: int, old_msg_id: Optional[int] = None) -> int:
    """Собрать дашборд и отправить в chat_id. Удалить old_msg_id если задан. Обновить user_dashboard."""
    try:
        live = await hass.get_all_live()
        battery_v = _safe_float(live.get("battery_voltage"))
        output_v = _safe_float(live.get("voltage"))
        is_on = str(live.get("switch", "")).lower() == "on"
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
        live = {}
        battery_v = output_v = i = p = ah = wh = temp_int = temp_ext = set_v = set_i = 0.0
        is_on = is_cv = is_cc = False
        mode = "ERROR"

    status_line, live_line, stage_block, capacity_line = _build_dashboard_blocks(live)
    short_status = (
        status_line.replace(" Mix Mode ", " Mix ")
        .replace(" Main Charge ", " Main ")
        .replace("Десульфатация", "Desulf")
        .replace("Безопасное ожидание", "Ожидание")
    )
    caption_short = f"{short_status}\n{live_line}"
    off_line = _format_manual_off_for_dashboard()
    if off_line:
        caption_short += f"\n{off_line}"

    graph_since = (
        charge_controller.total_start_time
        if charge_controller.is_active and getattr(charge_controller, "total_start_time", None)
        else None
    )
    limit_pts = 200 if graph_since else 100
    times, voltages, currents = await get_graph_data(limit=limit_pts, since_timestamp=graph_since)
    buf = generate_chart(times, voltages, currents)
    photo = BufferedInputFile(buf.getvalue(), filename="chart.png") if buf else None

    main_btn_text = "🛑 ОСТАНОВИТЬ" if is_on else "🚀 ЗАПУСТИТЬ"
    kb_rows = [
        [
            InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="refresh"),
            InlineKeyboardButton(text="📋 Полная инфо", callback_data="info_full"),
        ],
        [
            InlineKeyboardButton(text="🧠 AI АНАЛИЗ", callback_data="ai_analysis"),
            InlineKeyboardButton(text="📝 ЛОГИ СОБЫТИЙ", callback_data="logs"),
        ],
        [
            InlineKeyboardButton(text=main_btn_text, callback_data="power_toggle"),
            InlineKeyboardButton(text="⚙️ РЕЖИМЫ", callback_data="charge_modes"),
        ],
    ]
    ikb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    if old_msg_id:
        try:
            await bot.delete_message(chat_id, old_msg_id)
        except Exception:
            pass

    clean_caption = caption_short.replace('<hr>', '___________________').replace('<hr/>', '___________________').replace('<hr />', '___________________')
    if photo:
        sent = await bot.send_photo(chat_id, photo=photo, caption=clean_caption, reply_markup=ikb, parse_mode=ParseMode.HTML)
    else:
        sent = await bot.send_message(chat_id, clean_caption, reply_markup=ikb, parse_mode=ParseMode.HTML)

    user_dashboard[user_id] = sent.message_id
    return sent.message_id


async def send_dashboard_to_chat(chat_id: int, user_id: int = 0) -> int:
    """Отправить дашборд в чат (последним сообщением). Используется после некритичных уведомлений."""
    old_msg_id = user_dashboard.get(user_id) if user_id else None
    return await _build_and_send_dashboard(chat_id, user_id, old_msg_id)


async def send_dashboard(message_or_call: Union[Message, CallbackQuery], old_msg_id: Optional[int] = None) -> int:
    """
    Сформировать и отправить дашборд.
    Anti-spam: при refresh удаляем старый message перед отправкой нового.
    """
    msg = message_or_call.message if isinstance(message_or_call, CallbackQuery) else message_or_call
    chat_id = msg.chat.id
    user_id = message_or_call.from_user.id if getattr(message_or_call, "from_user", None) else 0
    old = old_msg_id or user_dashboard.get(user_id)
    try:
        await msg.delete()
    except Exception:
        pass
    return await _build_and_send_dashboard(chat_id, user_id, old)


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

            # Алерт: заряд завершён (высокое U на АКБ, низкий I). При V < 14В (хранение) — не чаще 1 раза в час
            battery_v = _safe_float(live.get("battery_voltage"))
            if battery_v >= 13.5 and i < 0.1:
                cooldown = STORAGE_ALERT_COOLDOWN if battery_v < 14.0 else CHARGE_ALERT_COOLDOWN
                if last_charge_alert_at and (now - last_charge_alert_at) < cooldown:
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
            output_on = str(output_switch or "").lower() == "on"
            ovp_triggered = str(live.get("ovp_triggered", "")).lower() == "on"
            ocp_triggered = str(live.get("ocp_triggered", "")).lower() == "on"
            battery_mode = str(live.get("battery_mode", "")).lower() == "on"
            input_voltage = _safe_float(live.get("input_voltage"), 0.0)
            temp_int = _safe_float(live.get("temp_int"), 0.0)
            
            # v2.5 Умный watchdog: обновляем последнее известное состояние выхода
            if output_switch is not None and str(output_switch).lower() not in ("unavailable", "unknown", ""):
                charge_controller._last_known_output_on = (
                    output_switch is True or str(output_switch).lower() == "on"
                )
            # Фактические уставки прибора — для сохранения в сессию (восстановление после перезапуска/потери связи)
            set_v = _safe_float(live.get("set_voltage"))
            set_i = _safe_float(live.get("set_current"))
            if set_v > 0 and set_i > 0:
                charge_controller._device_set_voltage = set_v
                charge_controller._device_set_current = set_i
            
            # Синхронизация общего времени заряда с прибором: sensor.rd_6018_uptime может быть датой старта (ISO)
            if charge_controller.is_active and live.get("uptime") is not None:
                elapsed = _parse_uptime_to_elapsed_sec(live.get("uptime"))
                if elapsed is not None and 0 < elapsed <= UPTIME_AS_CHARGE_TIMER_MAX_SEC:
                    charge_controller.total_start_time = time.time() - elapsed
            
            # Реакция на срабатывание OVP/OCP: лог, уведомление, выключение
            if charge_controller.is_active and (ovp_triggered or ocp_triggered):
                if ovp_triggered:
                    log_event(charge_controller.current_stage, battery_v, i, t, ah, "OVP_TRIGGERED")
                    _charge_notify("🛑 Сработала защита OVP (перенапряжение). Выход выключен.")
                if ocp_triggered:
                    log_event(charge_controller.current_stage, battery_v, i, t, ah, "OCP_TRIGGERED")
                    _charge_notify("🛑 Сработала защита OCP (переток). Выход выключен.")
                await hass.turn_off(ENTITY_MAP["switch"])
                charge_controller.stop()
            
            # Предкритическая температура блока: выключение выхода
            if (output_on or charge_controller.is_active) and temp_int >= TEMP_INT_PRECRITICAL:
                log_event(
                    charge_controller.current_stage,
                    battery_v,
                    i,
                    t,
                    ah,
                    f"TEMP_INT_PRECRITICAL_{temp_int:.0f}C",
                )
                _charge_notify(
                    f"🌡 Температура блока {temp_int:.0f}°C ≥ {TEMP_INT_PRECRITICAL:.0f}°C. "
                    "Выход выключен для защиты БП."
                )
                await hass.turn_off(ENTITY_MAP["switch"])
                charge_controller.stop()
            
            # Команда off: выключить по напряжению / току / таймеру (защиты не отключаются)
            if output_on and _has_manual_off_condition():
                now_ts = time.time()
                off_reason = None
                # «Достигли» V: оба порога заданы и равны — выкл при |V - value| <= eps
                if (
                    manual_off_voltage is not None
                    and manual_off_voltage_le is not None
                    and abs(manual_off_voltage - manual_off_voltage_le) < 0.01
                ):
                    if abs(battery_v - manual_off_voltage) <= OFF_REACH_EPS:
                        off_reason = f"напряжение достигло {manual_off_voltage:.2f} В (сейчас {battery_v:.2f} В)"
                elif manual_off_voltage is not None and battery_v >= manual_off_voltage:
                    off_reason = f"напряжение {battery_v:.2f} В ≥ {manual_off_voltage:.1f} В"
                elif manual_off_voltage_le is not None and battery_v <= manual_off_voltage_le:
                    off_reason = f"напряжение {battery_v:.2f} В ≤ {manual_off_voltage_le:.1f} В"
                # «Достигли» I: оба порога заданы и равны — выкл при |I - value| <= eps
                if off_reason is None:
                    if (
                        manual_off_current is not None
                        and manual_off_current_ge is not None
                        and abs(manual_off_current - manual_off_current_ge) < 0.01
                    ):
                        if abs(i - manual_off_current) <= OFF_REACH_EPS:
                            off_reason = f"ток достиг {manual_off_current:.2f} А (сейчас {i:.2f} А)"
                    elif manual_off_current is not None and i <= manual_off_current:
                        off_reason = off_reason or f"ток {i:.2f} А ≤ {manual_off_current:.2f} А"
                    elif manual_off_current_ge is not None and i >= manual_off_current_ge:
                        off_reason = off_reason or f"ток {i:.2f} А ≥ {manual_off_current_ge:.2f} А"
                if manual_off_time_sec is not None and (now_ts - manual_off_start_time) >= manual_off_time_sec:
                    off_reason = off_reason or f"таймер {manual_off_time_sec / 3600:.1f} ч"
                if off_reason:
                    log_event(charge_controller.current_stage, battery_v, i, t, ah, f"MANUAL_OFF_{off_reason[:30]}")
                    _charge_notify(f"⏹ Выключено по условию: {off_reason}")
                    await hass.turn_off(ENTITY_MAP["switch"])
                    charge_controller.stop()
                    _clear_manual_off()
            
            await add_record(battery_v, i, p, t)

            # Восстановление после потери связи: нет OVP/OCP, вход ≥ 60 В (battery_mode не требуем — после потери связи мы сами выключили выход)
            if temp_ext is not None and temp_ext not in ("unavailable", "unknown", ""):
                if charge_controller._was_unavailable and charge_controller.current_stage == charge_controller.STAGE_IDLE:
                    ok, msg = charge_controller.try_restore_session(battery_v, i, ah)
                    if ok and msg:
                        _apply_restore_time_corrections(charge_controller, live)
                        last_checkpoint_time = time.time()
                        allow_turn_on = (
                            not ovp_triggered
                            and not ocp_triggered
                            and input_voltage >= MIN_INPUT_VOLTAGE
                        )
                        if allow_turn_on:
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
                            _charge_notify("✅ Связь восстановлена, заряд снова под управлением бота.\n" + (msg or ""), critical=False)
                            logger.info("Session restored after link recovery: %s", charge_controller.current_stage)
                        else:
                            if ovp_triggered or ocp_triggered:
                                _charge_notify(
                                    "⚠️ Недавно сработала защита OVP/OCP. "
                                    "Включите заряд вручную после проверки."
                                )
                            elif input_voltage < MIN_INPUT_VOLTAGE:
                                _charge_notify(
                                    f"⚠️ Низкое входное напряжение ({input_voltage:.0f} В < {MIN_INPUT_VOLTAGE:.0f} В). "
                                    "Включите заряд вручную после проверки питания."
                                )
                            logger.info("Restore skipped: protections or input_voltage")
                    else:
                        # Нет файла сессии или старше 24 ч — выход может быть всё ещё вкл
                        if output_on and i > 0.05:
                            _charge_notify(
                                "⚠️ Связь восстановлена, но сессии нет (или старше 24 ч). "
                                f"Выход включён ({i:.2f} А). Нажмите Остановить или запустите заряд заново."
                            )
                            logger.warning("Link restored but no session; output still on I=%.2fA", i)

            # Выход уже включён, но бот в IDLE (перезапуск бота или ручное включение) — подхватываем сессию без turn_on
            if (
                temp_ext is not None
                and temp_ext not in ("unavailable", "unknown", "")
                and not charge_controller._was_unavailable
                and charge_controller.current_stage == charge_controller.STAGE_IDLE
                and output_on
                and i > 0.05
            ):
                ok, msg = charge_controller.try_restore_session(battery_v, i, ah)
                if ok and msg:
                    _apply_restore_time_corrections(charge_controller, live)
                    allow = (
                        not ovp_triggered
                        and not ocp_triggered
                        and input_voltage >= MIN_INPUT_VOLTAGE
                    )
                    if allow:
                        last_checkpoint_time = time.time()
                        if charge_controller.current_stage == charge_controller.STAGE_SAFE_WAIT:
                            uv, ui = charge_controller._safe_wait_target_v, charge_controller._safe_wait_target_i
                        else:
                            uv, ui = charge_controller._get_target_v_i()
                        await hass.set_voltage(uv)
                        await hass.set_current(ui)
                        log_event(
                            charge_controller.current_stage,
                            battery_v,
                            i,
                            t,
                            ah,
                            "RESTORE",
                        )
                        _charge_notify("✅ Заряд подхвачен, бот снова управляет.", critical=False)
                        logger.info("Session restored (output was already on): %s", charge_controller.current_stage)
                    else:
                        logger.debug("Restore (output on, idle) skipped: allow=%s ovp=%s ocp=%s input_v=%.0f", allow, ovp_triggered, ocp_triggered, input_voltage)
                else:
                    logger.debug("Restore (output on, idle): try_restore_session returned ok=%s (нет файла или сессия старше 24 ч)", ok)

            actions = await charge_controller.tick(
                battery_v, i, temp_ext, is_cv, ah, output_switch,
                manual_off_active=_has_manual_off_condition(),
            )

            end = actions.get("log_event_end")
            if end:
                log_stage_end(
                    end["stage"],
                    end["v"],
                    end["i"],
                    end["t"],
                    end["ah"],
                    end["time_sec"],
                    end["ah_on_stage"],
                    end["trigger"],
                )
            if actions.get("log_event_sub"):
                log_event(
                    end["stage"] if end else charge_controller.current_stage,
                    battery_v,
                    i,
                    t,
                    ah,
                    actions["log_event_sub"],
                )
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
            
            # Очистка БД и журнала событий каждые 24 часа (записи старше 30 дней)
            if now_ts - last_cleanup_time >= 86400:  # 24 часа
                await cleanup_old_records()
                try:
                    trim_log_older_than_days(30)
                except Exception as ex:
                    logger.warning("trim_log_older_than_days: %s", ex)
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
            charge_controller._was_unavailable = True
            charge_controller._link_lost_at = time.time()

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
    if not await _check_chat_and_respond(message):
        return
    global last_chat_id, last_user_id
    last_chat_id = message.chat.id
    last_user_id = message.from_user.id if message.from_user else 0
    logger.info("Command /start from %s", message.from_user.id)
    msg_id = await send_dashboard(message)
    if message.from_user:
        user_dashboard[message.from_user.id] = msg_id


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """Статистика и прогноз перенесены в «Полная инфо»."""
    if not await _check_chat_and_respond(message):
        return
    await message.answer(
        "📋 Статистика и прогноз заряда теперь в блоке <b>«Полная инфо»</b> — нажмите кнопку под графиком.",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("entities"))
async def cmd_entities(message: Message) -> None:
    """Опросить и показать статус всех сущностей Home Assistant (RD6018)."""
    if not await _check_chat_and_respond(message):
        return
    status_msg = await message.answer("⏳ Опрашиваю сущности HA...", parse_mode=ParseMode.HTML)
    try:
        rows = await hass.get_entities_status()
        lines = ["<b>📡 Статус сущностей RD6018</b>\n"]
        ok_count = sum(1 for r in rows if r["status"] == "ok")
        bad = [r for r in rows if r["status"] != "ok"]
        lines.append(f"✅ Доступно: {ok_count}/{len(rows)}")
        if bad:
            lines.append(f"⚠️ Нет данных: {len(bad)}\n")
        for r in rows:
            key = html.escape(r["key"])
            eid = html.escape(r["entity_id"])
            state = html.escape(str(r["state"]))
            unit = html.escape(r["unit"] or "")
            status = r["status"]
            if status == "ok":
                icon = "🟢"
                line = f"{icon} <b>{key}</b>: {state} {unit}".strip()
            else:
                icon = "🔴" if status == "error" else "🟡"
                line = f"{icon} <b>{key}</b>: {status} ({state})"
            lines.append(line)
        text = "\n".join(lines)
        if len(text) > 4000:
            text = "\n".join(lines[:2] + [f"… всего {len(rows)} сущностей, обрезка"] + [l for l in lines[3:25]])
        await status_msg.edit_text(text, parse_mode=ParseMode.HTML)
    except Exception as ex:
        logger.exception("cmd_entities: %s", ex)
        await status_msg.edit_text(
            f"❌ Ошибка опроса сущностей: {html.escape(str(ex))}",
            parse_mode=ParseMode.HTML,
        )


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
        
        # Явный флаг статуса выхода для AI (Output ON/OFF)
        output_status = "ON" if output_on else "OFF"
        
        # Формируем полный контекст
        context = f"""ПОЛНЫЙ СЛЕПОК RD6018:

OUTPUT_STATUS: {output_status} (выход зарядного устройства: включен/выключен)

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


# Порог «достигли» для выключения по V или I (с любой стороны)
OFF_REACH_EPS = 0.02


def _parse_three_values(text: str) -> Optional[Dict[str, Any]]:
    """
    Парсит строку из трёх частей: V I и третья — таймер H:MM, ток X.XXA/А, или напряжение X.XV/В.
    Возвращает dict с v, i и одним из: time_sec, off_current, off_voltage; иначе None.
    """
    parts = (text or "").strip().replace(",", ".").split()
    if len(parts) != 3:
        return None
    try:
        v = float(parts[0])
        i = float(parts[1])
        third = parts[2].strip().upper().rstrip("AАВV")
        if not third:
            return None
        # Таймер: 2:35 или 2:35:00
        if ":" in parts[2]:
            comp = parts[2].split(":")
            if len(comp) == 2:
                h, m = int(comp[0].strip()), int(comp[1].strip())
                time_sec = h * 3600 + m * 60
            elif len(comp) == 3:
                h, m, s = int(comp[0].strip()), int(comp[1].strip()), int(comp[2].strip())
                time_sec = h * 3600 + m * 60 + s
            else:
                return None
            if time_sec <= 0:
                return None
            return {"v": v, "i": i, "time_sec": time_sec}
        # Ток: 2.35A / 2.35А (латиница или кириллица) — выкл по достижении тока
        raw3 = parts[2].strip().replace(",", ".")
        last_char = (raw3[-1].upper() if len(raw3) > 1 else "")
        if last_char in ("A", "А"):  # A (Latin) или А (Cyrillic)
            val = float(third)
            if 0.1 <= val <= 18.0:
                return {"v": v, "i": i, "off_current": val}
            return None
        # Напряжение: 15V / 15В (латиница или кириллица) — выкл по достижении напряжения
        if last_char in ("V", "В"):  # V (Latin) или В (Cyrillic)
            val = float(third)
            if 0 <= val <= 20.0:
                return {"v": v, "i": i, "off_voltage": val}
            return None
    except (ValueError, IndexError):
        pass
    return None


def _parse_two_numbers(text: str) -> Optional[tuple]:
    """Парсит строку вида '16.50 1.4' (напряжение и ток). Возвращает (v, i) или None."""
    parts = (text or "").strip().replace(",", ".").split()
    if len(parts) != 2:
        return None
    try:
        v = float(parts[0])
        i = float(parts[1])
        return (v, i)
    except ValueError:
        return None


@router.message(F.text)
async def text_message_handler(message: Message) -> None:
    """v2.6 Обработка текстовых сообщений: ввод ёмкости АКБ, ручной режим или режим диалога с LLM."""
    if not await _check_chat_and_respond(message):
        return
    global awaiting_ah, custom_mode_state, last_chat_id, last_checkpoint_time
    user_id = message.from_user.id if message.from_user else 0
    text = (message.text or "").strip()

    # Команда off: выключить по напряжению / току / таймеру (вне ручного режима)
    if not (user_id in custom_mode_state or awaiting_ah.get(user_id)):
        off_parsed = _parse_off_command(text)
        if off_parsed is not None:
            global manual_off_voltage, manual_off_voltage_le, manual_off_current, manual_off_current_ge, manual_off_time_sec, manual_off_start_time
            manual_off_voltage = off_parsed.get("voltage_ge")
            manual_off_voltage_le = off_parsed.get("voltage_le")
            manual_off_current = off_parsed.get("current_le")
            manual_off_current_ge = off_parsed.get("current_ge")
            manual_off_time_sec = off_parsed.get("time_sec")
            manual_off_start_time = off_parsed["start_time"]
            _save_manual_off_state()
            cond = ", ".join(off_parsed["parts"])
            await message.answer(
                f"✅ <b>Выключение по условию:</b> {cond}",
                parse_mode=ParseMode.HTML,
            )
            last_chat_id = message.chat.id
            return
        if text.strip().lower() == "off":
            _clear_manual_off()
            await message.answer("Сброс условия выключения. Уставки «off» больше не активны.")
            last_chat_id = message.chat.id
            return

    # Три значения: V I и таймер (2:35), или ток 2.35A/А, или напряжение 15V/В — уставки + условие выключения
    if not (user_id in custom_mode_state or awaiting_ah.get(user_id)):
        three = _parse_three_values(text)
        if three is not None:
            v_set, i_set = three["v"], three["i"]
            if 12.0 <= v_set <= 17.0 and 0.1 <= i_set <= 18.0:
                ok_v = await hass.set_voltage(v_set)
                ok_i = await hass.set_current(i_set)
                global manual_off_voltage, manual_off_voltage_le, manual_off_current, manual_off_current_ge, manual_off_time_sec, manual_off_start_time
                manual_off_voltage = None
                manual_off_voltage_le = None
                manual_off_current = None
                manual_off_current_ge = None
                manual_off_time_sec = None
                if "time_sec" in three:
                    manual_off_time_sec = three["time_sec"]
                    manual_off_start_time = time.time()
                    cond = f"таймер {manual_off_time_sec / 3600:.1f} ч"
                elif "off_current" in three:
                    manual_off_current = three["off_current"]
                    manual_off_current_ge = three["off_current"]
                    cond = f"при достижении тока {three['off_current']:.2f} А"
                else:
                    manual_off_voltage = three["off_voltage"]
                    manual_off_voltage_le = three["off_voltage"]
                    cond = f"при достижении напряжения {three['off_voltage']:.2f} В"
                _save_manual_off_state()
                on_dev = ""
                if ok_v and ok_i:
                    await asyncio.sleep(0.8)
                    live = await hass.get_all_live()
                    on_v = _safe_float(live.get("set_voltage"), 0.0)
                    on_i = _safe_float(live.get("set_current"), 0.0)
                    on_dev = f" На приборе: {on_v:.2f} В | {on_i:.2f} А"
                else:
                    on_dev = " ⚠️ Проверьте уставки на приборе."
                await message.answer(
                    f"✅ Уставки: {v_set:.1f} В, {i_set:.2f} А. Выключение: {cond}.{on_dev}",
                    parse_mode=ParseMode.HTML,
                )
                last_chat_id = message.chat.id
                return
            else:
                await message.answer("Диапазоны: напряжение 12–17 В, ток 0.1–18 А.")
                last_chat_id = message.chat.id
                return

    # Быстрая установка уставок: два числа через пробел — напряжение (В) и ток (А)
    # Не перехватываем, если пользователь в диалоге выбора режима или ввода ёмкости
    if not (user_id in custom_mode_state or awaiting_ah.get(user_id)):
        parsed = _parse_two_numbers(text)
        if parsed is not None:
            v_set, i_set = parsed
            if 12.0 <= v_set <= 17.0 and 0.1 <= i_set <= 18.0:
                ok_v = await hass.set_voltage(v_set)
                ok_i = await hass.set_current(i_set)
                if not ok_v or not ok_i:
                    await message.answer(
                        f"⚠️ Ошибка отправки в HA: напряжение — {'ок' if ok_v else 'ошибка'}, ток — {'ок' if ok_i else 'ошибка'}. Проверьте связь с Home Assistant.",
                        parse_mode=ParseMode.HTML,
                    )
                    last_chat_id = message.chat.id
                    return
                await asyncio.sleep(0.8)
                live = await hass.get_all_live()
                on_v = _safe_float(live.get("set_voltage"), 0.0)
                on_i = _safe_float(live.get("set_current"), 0.0)
                tol = 0.02
                match = abs(on_v - v_set) <= tol and abs(on_i - i_set) <= tol
                if match:
                    await message.answer(
                        f"✅ <b>Уставки установлены:</b> {v_set:.2f} В | {i_set:.2f} А\n"
                        f"📟 На приборе: {on_v:.2f} В | {on_i:.2f} А",
                        parse_mode=ParseMode.HTML,
                    )
                else:
                    await message.answer(
                        f"✅ Уставки отправлены в HA: {v_set:.2f} В | {i_set:.2f} А\n"
                        f"📟 На приборе сейчас: {on_v:.2f} В | {on_i:.2f} А\n"
                        "⚠️ Значения на приборе отличаются — проверьте интеграцию RD6018 и связь.",
                        parse_mode=ParseMode.HTML,
                    )
                last_chat_id = message.chat.id
                return
            await message.answer(
                "⚠️ Допустимые диапазоны: напряжение 12–17 В, ток 0.1–18 А. Пример: <code>16.50 1.4</code>",
                parse_mode=ParseMode.HTML,
            )
            return

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
    last_user_id = message.from_user.id if message.from_user else 0
    live = await hass.get_all_live()
    battery_v = _safe_float(live.get("battery_voltage"))
    i = _safe_float(live.get("current"))
    t = _safe_float(live.get("temp_ext"))
    ah_val = _safe_float(live.get("ah"))
    input_v = _safe_float(live.get("input_voltage"), 0.0)
    if t < MIN_START_TEMP:
        await message.answer(
            f"❌ Заряд не запущен: температура внешнего датчика {t:.1f}°C ниже {MIN_START_TEMP:.0f}°C. "
            "Прогрейте АКБ или помещение.",
            parse_mode=ParseMode.HTML,
        )
        return
    if input_v > 0 and input_v < MIN_INPUT_VOLTAGE:
        log_event("Idle", battery_v, i, t, ah_val, f"START_REFUSED_INPUT_VOLTAGE_{input_v:.0f}V")
        await message.answer(
            f"❌ Заряд не запущен: входное напряжение {input_v:.0f} В ниже {MIN_INPUT_VOLTAGE:.0f} В. "
            "Проверьте питание БП.",
            parse_mode=ParseMode.HTML,
        )
        return
    charge_controller.start(profile, ah)
    # Устанавливаем стартовые уставки и OVP/OCP под новый профиль
    if battery_v < 12.0:
        uv, ui = 12.0, 0.5
    else:
        uv, ui = charge_controller._main_target()

    await hass.set_voltage(uv)
    await hass.set_current(ui)
    await hass.set_ovp(uv + OVP_OFFSET)
    await hass.set_ocp(ui + OCP_OFFSET)
    await hass.turn_on(ENTITY_MAP["switch"])
    last_checkpoint_time = time.time()
    # Лог "Подготовка: START" пишется при первом tick()
    await message.answer(
        f"<b>✅ Заряд запущен:</b> {profile} {ah}Ач\n"
        f"Текущая фаза: <b>{charge_controller.current_stage}</b>",
        parse_mode=ParseMode.HTML,
    )
    old_id = user_dashboard.get(user_id)
    msg_id = await send_dashboard(message, old_msg_id=old_id)
    if user_id:
        user_dashboard[user_id] = msg_id

    # Через 2 секунды после включения выхода — автообновление дашборда
    async def _delayed_dashboard_refresh() -> None:
        try:
            await asyncio.sleep(2)
            old = user_dashboard.get(user_id)
            new_id = await send_dashboard(message, old_msg_id=old)
            if user_id:
                user_dashboard[user_id] = new_id
        except Exception as ex:
            logger.warning("Delayed dashboard refresh failed: %s", ex)

    asyncio.create_task(_delayed_dashboard_refresh())


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
        
        # Системный промпт для эксперта-аккумуляторщика (из ai_system_prompt.py)
        system_prompt = AI_CONSULTANT_SYSTEM_PROMPT

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
    
    # В шаге "voltage" допускаем ввод двух чисел через пробел: "16.50 1.4" (В и А)
    if state == "voltage":
        two = _parse_two_numbers(text)
        if two is not None:
            v_val, i_val = two
            if 12.0 <= v_val <= 17.0 and 0.1 <= i_val <= 18.0:
                custom_mode_data[user_id]["main_voltage"] = v_val
                custom_mode_data[user_id]["main_current"] = i_val
                custom_mode_state[user_id] = "delta"
                custom_mode_confirm.pop(user_id, None)
                await message.answer(
                    f"✅ Main: {v_val:.1f}В / {i_val:.1f}А\n\n"
                    "**Шаг 3/5:** Введите дельту (0.01 - 0.05):\n"
                    "_Чем меньше, тем чувствительнее финиш. Стандарт: 0.03_",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=cancel_kb
                )
                return
            await message.answer(
                "⚠️ Допустимые диапазоны: напряжение 12–17 В, ток 0.1–18 А. Введите заново (например 16.50 1.4):",
                reply_markup=cancel_kb
            )
            return
    
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
    global last_chat_id, last_user_id, last_checkpoint_time
    last_chat_id = message.chat.id
    last_user_id = message.from_user.id if message.from_user else 0
    try:
        # Получаем текущие данные
        live = await hass.get_all_live()
        battery_v = _safe_float(live.get("battery_voltage", 12.0))
        i = _safe_float(live.get("current", 0.0))
        t = _safe_float(live.get("temp_ext", 25.0))
        ah_val = _safe_float(live.get("ah", 0.0))
        input_v = _safe_float(live.get("input_voltage"), 0.0)
        if t < MIN_START_TEMP:
            await message.answer(
                f"❌ Заряд не запущен: температура внешнего датчика {t:.1f}°C ниже {MIN_START_TEMP:.0f}°C. "
                "Прогрейте АКБ или помещение.",
                parse_mode=ParseMode.HTML,
            )
            return
        if input_v > 0 and input_v < MIN_INPUT_VOLTAGE:
            log_event("Idle", battery_v, i, t, ah_val, f"START_REFUSED_INPUT_VOLTAGE_{input_v:.0f}V")
            await message.answer(
                f"❌ Заряд не запущен: входное напряжение {input_v:.0f} В ниже {MIN_INPUT_VOLTAGE:.0f} В. "
                "Проверьте питание БП.",
                parse_mode=ParseMode.HTML,
            )
            return
        # Запускаем контроллер в ручном режиме
        charge_controller.start_custom(
            main_voltage=params["main_voltage"],
            main_current=params["main_current"],
            delta_threshold=params["delta"],
            time_limit_hours=params["time_limit"],
            ah_capacity=int(params["capacity"])
        )
        
        # Устанавливаем параметры на RD6018 и сбрасываем OVP/OCP под пользовательский профиль
        await hass.set_voltage(params["main_voltage"])
        await hass.set_current(params["main_current"])
        await hass.set_ovp(params["main_voltage"] + OVP_OFFSET)
        await hass.set_ocp(params["main_current"] + OCP_OFFSET)
        await hass.turn_on(ENTITY_MAP["switch"])
        
        last_checkpoint_time = time.time()
        log_event(
            "Подготовка",
            battery_v,
            i,
            t,
            ah_val,
            (
                f"START CUSTOM main={params['main_voltage']:.1f}V/{params['main_current']:.1f}A "
                f"delta={params['delta']:.3f}V limit={params['time_limit']:.0f}h ah={params['capacity']:.0f}"
            ),
        )
        
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
        msg_id = await send_dashboard(message, old_msg_id=old_id)
        if user_id:
            user_dashboard[user_id] = msg_id

        # Автообновление через 2 секунды после включения выхода
        async def _delayed_dashboard_refresh_custom() -> None:
            try:
                await asyncio.sleep(2)
                old = user_dashboard.get(user_id)
                new_id = await send_dashboard(message, old_msg_id=old)
                if user_id:
                    user_dashboard[user_id] = new_id
            except Exception as ex:
                logger.warning("Delayed dashboard refresh (custom) failed: %s", ex)

        asyncio.create_task(_delayed_dashboard_refresh_custom())
        
    except Exception as ex:
        logger.error("start_custom_charge error: %s", ex)
        await message.answer("❌ Ошибка запуска ручного режима. Проверьте подключение к RD6018.")


@router.callback_query(F.data == "charge_modes")
async def charge_modes_handler(call: CallbackQuery) -> None:
    """Открыть подменю «🚗 Авто» с режимами заряда."""
    if not await _check_chat_and_respond(call):
        return
    try:
        await call.answer()
    except Exception:
        pass
    global last_chat_id, last_user_id
    last_chat_id = call.message.chat.id
    last_user_id = call.from_user.id if call.from_user else 0
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
            [
                InlineKeyboardButton(text="🛠 Ручной режим", callback_data="profile_custom"),
                InlineKeyboardButton(text="⏹ Off по условию", callback_data="menu_off"),
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


@router.callback_query(F.data == "custom_cancel")
async def custom_mode_cancel(call: CallbackQuery) -> None:
    """Отменить ручной режим и вернуться в главное меню."""
    if not await _check_chat_and_respond(call):
        return
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
    if not await _check_chat_and_respond(call):
        return
    try:
        await call.answer()
    except Exception:
        pass
    old_id = user_dashboard.get(call.from_user.id) if call.from_user else None
    await send_dashboard(call, old_msg_id=old_id)


@router.callback_query(F.data == "menu_off")
async def menu_off_handler(call: CallbackQuery) -> None:
    """Меню «Off по условию»: показать статус и подсказку по команде."""
    if not await _check_chat_and_respond(call):
        return
    try:
        await call.answer()
    except Exception:
        pass
    off_line = _format_manual_off_for_dashboard()
    if off_line:
        status_msg = f"<b>⏹ Принудительное выключение активно</b>\n\n{off_line}\n\n"
    else:
        status_msg = "Сейчас условие выключения не задано.\n\n"
    status_msg += (
        "<b>Введите в чат:</b>\n"
        "• <code>off I&lt;=1.23</code> или <code>off 1.23</code> — выкл при токе ≤1.23 А\n"
        "• <code>off I&gt;=2</code> — выкл при токе ≥2 А\n"
        "• <code>off V&gt;=16.4</code> или <code>off 16.4</code> — выкл при напряжении ≥16.4 В\n"
        "• <code>off V&lt;=13.2</code> — выкл при напряжении ≤13.2 В (микс)\n"
        "• <code>off 2:23</code> — выкл через 2 ч 23 мин\n"
        "• <code>off I&gt;=2 V&lt;=13.5 2:00</code> — любое из условий\n"
        "• <code>off</code> — сброс\n\n"
        "Защиты не сбрасываются; температура и входное напряжение могут выключить выход раньше."
    )
    await call.message.answer(status_msg, parse_mode=ParseMode.HTML)
    old_id = user_dashboard.get(call.from_user.id) if call.from_user else None
    await send_dashboard(call, old_msg_id=old_id)


@router.callback_query(F.data == "info_full")
async def info_full_handler(call: CallbackQuery) -> None:
    if not await _check_chat_and_respond(call):
        return
    try:
        await call.answer()
    except Exception:
        pass
    try:
        live = await hass.get_all_live()
        status_line, live_line, stage_block, capacity_line = _build_dashboard_blocks(live)
        full_text = f"{status_line}\n{live_line}{stage_block}\n{capacity_line}"
        off_line = _format_manual_off_for_dashboard()
        if off_line:
            full_text += f"\n{off_line}"
        full_text += f"\n⏱ Таймер прибора (sensor.rd_6018_uptime): {_format_uptime_display(live.get('uptime'))}"
        ovp_tr = str(live.get("ovp_triggered", "")).lower() == "on"
        ocp_tr = str(live.get("ocp_triggered", "")).lower() == "on"
        full_text += f"\n🛡 Защиты: OVP сработала — {'да' if ovp_tr else 'нет'}, OCP сработала — {'да' if ocp_tr else 'нет'}"
        # Статистика и прогноз заряда (из бывшего /stats)
        battery_v = _safe_float(live.get("battery_voltage"))
        i = _safe_float(live.get("current"))
        ah = _safe_float(live.get("ah"))
        temp = _safe_float(live.get("temp_ext"))
        if charge_controller.is_active:
            stats = charge_controller.get_stats(battery_v, i, ah, temp)
            stats_block = (
                "\n──────────────────\n"
                "📊 <b>СТАТИСТИКА И ПРОГНОЗ</b>\n"
                f"🔋 Этап: {stats['stage']}\n"
                f"⏱ В работе: {stats['elapsed_time']}\n"
                f"📥 Залито: {stats['ah_total']:.2f} Ач\n"
                f"🌡 Темп: {stats['temp_ext']:.1f}°C ({stats['temp_trend']})\n"
                f"🔮 Завершение через {stats['predicted_time']}\n"
                f"<i>{stats['comment']}</i>"
            )
            if stats.get("health_warning"):
                stats_block += f"\n\n{stats['health_warning']}"
            full_text += stats_block
        full_text = full_text.replace("<hr>", "___________________").replace("<hr/>", "___________________").replace("<hr />", "___________________")
        caption = f"<b>📋 Полная информация по режиму</b>\n\n{full_text}"
        # График как в краткой инфо
        graph_since = (
            charge_controller.total_start_time
            if charge_controller.is_active and getattr(charge_controller, "total_start_time", None)
            else None
        )
        limit_pts = 200 if graph_since else 100
        times, voltages, currents = await get_graph_data(limit=limit_pts, since_timestamp=graph_since)
        buf = generate_chart(times, voltages, currents)
        photo = BufferedInputFile(buf.getvalue(), filename="chart.png") if buf else None
        is_on = str(live.get("switch", "")).lower() == "on"
        main_btn_text = "🛑 ОСТАНОВИТЬ" if is_on else "🚀 ЗАПУСТИТЬ"
        kb_rows = [
            [
                InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="refresh"),
                InlineKeyboardButton(text="📋 Полная инфо", callback_data="info_full"),
            ],
            [
                InlineKeyboardButton(text="🧠 AI АНАЛИЗ", callback_data="ai_analysis"),
                InlineKeyboardButton(text="📝 ЛОГИ СОБЫТИЙ", callback_data="logs"),
            ],
            [
                InlineKeyboardButton(text=main_btn_text, callback_data="power_toggle"),
                InlineKeyboardButton(text="⚙️ РЕЖИМЫ", callback_data="charge_modes"),
            ],
        ]
        ikb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
        if photo:
            await call.message.answer_photo(photo=photo, caption=caption, reply_markup=ikb, parse_mode=ParseMode.HTML)
        else:
            await call.message.answer(caption, reply_markup=ikb, parse_mode=ParseMode.HTML)
        # Ниже — аналитика DeepSeek по телеметрии (тот же промпт, что был в /stats)
        if charge_controller.is_active:
            telemetry = charge_controller.get_telemetry_summary(battery_v, i, ah, temp)
            ai_comment = await call_llm_analytics(telemetry)
            if ai_comment:
                ai_safe = (ai_comment or "").replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
                ai_text = f"🤖 <b>Аналитика DeepSeek:</b>\n<i>{ai_safe}</i>"
            else:
                ai_text = "🤖 <b>Аналитика DeepSeek:</b> <i>Математический прогноз (API недоступен)</i>"
            try:
                await call.message.answer(ai_text, parse_mode=ParseMode.HTML)
            except Exception as ex_ai:
                logger.warning("info_full AI message: %s", ex_ai)
    except Exception as ex:
        logger.error("info_full: %s", ex)
        await call.message.answer("Не удалось загрузить данные.")


@router.callback_query(F.data == "entities_status")
async def entities_status_handler(call: CallbackQuery) -> None:
    """Показать статус всех сущностей HA по кнопке дашборда."""
    if not await _check_chat_and_respond(call):
        return
    try:
        await call.answer("Опрашиваю сущности...")
    except Exception:
        pass
    try:
        rows = await hass.get_entities_status()
        lines = ["<b>📡 Статус сущностей RD6018</b>\n"]
        ok_count = sum(1 for r in rows if r["status"] == "ok")
        lines.append(f"✅ Доступно: {ok_count}/{len(rows)}\n")
        for r in rows:
            key = html.escape(r["key"])
            state = html.escape(str(r["state"]))
            unit = html.escape(r["unit"] or "")
            status = r["status"]
            if status == "ok":
                icon = "🟢"
                line = f"{icon} <b>{key}</b>: {state} {unit}".strip()
            else:
                icon = "🔴" if status == "error" else "🟡"
                line = f"{icon} <b>{key}</b>: {status} ({state})"
            lines.append(line)
        text = "\n".join(lines)
        if len(text) > 4000:
            text = "\n".join(lines[:3] + [f"… всего {len(rows)} сущностей"] + [l for l in lines[3:25]])
        await call.message.answer(text, parse_mode=ParseMode.HTML)
    except Exception as ex:
        logger.exception("entities_status_handler: %s", ex)
        await call.message.answer(f"❌ Ошибка опроса: {html.escape(str(ex))}", parse_mode=ParseMode.HTML)


@router.callback_query(F.data == "refresh")
async def refresh_handler(call: CallbackQuery) -> None:
    if not await _check_chat_and_respond(call):
        return
    try:
        await call.answer("Информация обновлена")
    except Exception:
        pass
    global last_chat_id, last_user_id
    last_chat_id = call.message.chat.id
    last_user_id = call.from_user.id if call.from_user else 0
    old_id = user_dashboard.get(call.from_user.id) if call.from_user else None
    await send_dashboard(call, old_msg_id=old_id)


@router.callback_query(F.data == "power_toggle")
async def power_toggle_handler(call: CallbackQuery) -> None:
    if not await _check_chat_and_respond(call):
        return
    try:
        await call.answer()
    except Exception:
        pass
    global last_chat_id, last_user_id
    last_chat_id = call.message.chat.id
    last_user_id = call.from_user.id if call.from_user else 0
    live = await hass.get_all_live()
    is_on = str(live.get("switch", "")).lower() == "on"
    # Если заряд активен или выход включен — останавливаем заряд и выключаем выход
    if charge_controller.is_active or is_on:
        charge_controller.stop()
        _clear_manual_off()
        await hass.turn_off(ENTITY_MAP["switch"])
        await call.message.answer(
            "<b>🛑 Заряд остановлен.</b> Выход выключен.",
            parse_mode=ParseMode.HTML,
        )
    else:
        # Выход выключен: пробуем восстановить сессию, чтобы бот снова управлял зарядом
        battery_v = _safe_float(live.get("battery_voltage"))
        i = _safe_float(live.get("current"))
        ah = _safe_float(live.get("ah"))
        ovp_triggered = str(live.get("ovp_triggered", "")).lower() == "on"
        ocp_triggered = str(live.get("ocp_triggered", "")).lower() == "on"
        input_voltage = _safe_float(live.get("input_voltage"), 0.0)
        ok, msg = charge_controller.try_restore_session(battery_v, i, ah)
        if ok and msg:
            _apply_restore_time_corrections(charge_controller, live)
        allow_turn_on = ok and msg and not ovp_triggered and not ocp_triggered and input_voltage >= MIN_INPUT_VOLTAGE
        if allow_turn_on:
            if charge_controller.current_stage == charge_controller.STAGE_SAFE_WAIT:
                uv, ui = charge_controller._safe_wait_target_v, charge_controller._safe_wait_target_i
                await hass.set_voltage(uv)
                await hass.set_current(ui)
            else:
                uv, ui = charge_controller._get_target_v_i()
                await hass.set_voltage(uv)
                await hass.set_current(ui)
            await hass.turn_on(ENTITY_MAP["switch"])
            await call.message.answer(
                "<b>🚀 Заряд подхвачен.</b> Сессия восстановлена, бот снова управляет этапами.",
                parse_mode=ParseMode.HTML,
            )
        else:
            await hass.turn_on(ENTITY_MAP["switch"])
            await call.message.answer(
                "<b>🚀 Выход включён</b> с текущими параметрами RD6018. "
                "Чтобы бот вёл этапы — выберите режим в <b>⚙️ РЕЖИМЫ</b>.",
                parse_mode=ParseMode.HTML,
            )
    await asyncio.sleep(1)
    old_id = user_dashboard.get(call.from_user.id) if call.from_user else None
    await send_dashboard(call, old_msg_id=old_id)


@router.callback_query(F.data == "profile_custom")
async def custom_mode_start(call: CallbackQuery) -> None:
    """Начать ручной режим с приветственным сообщением."""
    if not await _check_chat_and_respond(call):
        return
    try:
        await call.answer()
    except Exception:
        pass
    global custom_mode_state, custom_mode_data, last_chat_id, last_user_id
    last_chat_id = call.message.chat.id
    last_user_id = call.from_user.id if call.from_user else 0
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
    if not await _check_chat_and_respond(call):
        return
    try:
        await call.answer()
    except Exception:
        pass
    global awaiting_ah, last_chat_id, last_user_id
    last_chat_id = call.message.chat.id
    last_user_id = call.from_user.id if call.from_user else 0
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
    if not await _check_chat_and_respond(call):
        return
    try:
        await call.answer()
    except Exception:
        pass
    # Получаем реальные события из лога заряда
    from charging_log import get_recent_events
    try:
        recent_events = get_recent_events(20)  # Берем больше событий для фильтрации
        if not recent_events:
            text = "<b>📝 Логи событий</b>\n\nНет событий."
        else:
            # Удаляем дубли идущих подряд событий
            filtered_events = _remove_duplicate_events(recent_events)
            
            lines = ["<b>📝 Логи событий</b>\n"]
            for event in filtered_events[-15:]:  # Берем последние 15 после фильтрации
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

    # Обновление дашборда через 90 с (пауза до обновления информации)
    if call.from_user:
        user_id = call.from_user.id
        old_id = user_dashboard.get(user_id)

        async def _delayed_dashboard() -> None:
            await asyncio.sleep(90)
            try:
                msg_id = await send_dashboard(call, old_msg_id=old_id)
                user_dashboard[user_id] = msg_id
            except Exception as ex:
                logger.debug("delayed send_dashboard after logs: %s", ex)

        asyncio.create_task(_delayed_dashboard())


@router.callback_query(F.data == "ai_analysis")
async def ai_analysis_handler(call: CallbackQuery) -> None:
    if not await _check_chat_and_respond(call):
        return
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
    result_html = _md_to_html(result).replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    await status_msg.edit_text(f"<b>🧠 AI Анализ:</b>\n{result_html}", parse_mode=ParseMode.HTML)

    # Обновление дашборда через 90 с (пауза до обновления информации)
    if call.from_user:
        user_id = call.from_user.id
        old_id = user_dashboard.get(user_id)

        async def _delayed_dashboard_ai() -> None:
            await asyncio.sleep(90)
            try:
                msg_id = await send_dashboard(call, old_msg_id=old_id)
                user_dashboard[user_id] = msg_id
            except Exception as ex:
                logger.debug("delayed send_dashboard after ai_analysis: %s", ex)

        asyncio.create_task(_delayed_dashboard_ai())


async def main() -> None:
    await init_db()
    rotate_if_needed()
    # Очистка журнала событий от записей старше 30 дней
    try:
        n = trim_log_older_than_days(30)
        if n > 0:
            logger.info("Trimmed %d old lines from charging_history.log", n)
    except Exception as ex:
        logger.warning("trim_log_older_than_days at startup: %s", ex)

    _load_manual_off_state()

    # Auto-Resume: восстановить сессию, если charge_session.json < 60 мин и нет OVP/OCP, вход ≥ 60 В
    global last_checkpoint_time
    try:
        live = await hass.get_all_live()
        battery_v = _safe_float(live.get("battery_voltage"))
        i = _safe_float(live.get("current"))
        ah = _safe_float(live.get("ah"))
        ovp_triggered = str(live.get("ovp_triggered", "")).lower() == "on"
        ocp_triggered = str(live.get("ocp_triggered", "")).lower() == "on"
        input_voltage = _safe_float(live.get("input_voltage"), 0.0)
        ok, msg = charge_controller.try_restore_session(battery_v, i, ah)
        if ok and msg:
            _apply_restore_time_corrections(charge_controller, live)
            last_checkpoint_time = time.time()
            allow_turn_on = (
                not ovp_triggered
                and not ocp_triggered
                and input_voltage >= MIN_INPUT_VOLTAGE
            )
            if allow_turn_on:
                if charge_controller.current_stage == charge_controller.STAGE_SAFE_WAIT:
                    uv, ui = charge_controller._safe_wait_target_v, charge_controller._safe_wait_target_i
                    await hass.set_voltage(uv)
                    await hass.set_current(ui)
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
            else:
                logger.info(
                    "Auto-resume skipped: ovp=%s ocp=%s input_v=%.0f",
                    ovp_triggered, ocp_triggered, input_voltage,
                )
    except Exception as ex:
        logger.warning("Auto-resume check failed: %s", ex)

    dp.include_router(router)
    await bot.set_my_commands([
        BotCommand(command="start", description="Открыть дашборд RD6018"),
        BotCommand(command="entities", description="Статус сущностей HA (RD6018)"),
    ])
    asyncio.create_task(data_logger())
    asyncio.create_task(charge_monitor())
    asyncio.create_task(soft_watchdog_loop())
    asyncio.create_task(watchdog_loop())
    logger.info("RD6018 bot starting")
    logger.info("Если появится TelegramConflictError — запущен ещё один экземпляр бота. Остановите все кроме одного: pgrep -af 'bot.py' && kill <PID>")
    try:
        await dp.start_polling(bot)
    finally:
        await hass.close()
        try:
            session = getattr(bot, "session", None)
            if session is not None and not getattr(session, "closed", True):
                await session.close()
        except Exception as ex:
            logger.debug("Bot session close: %s", ex)
        logger.info("RD6018 bot stopped")


if __name__ == "__main__":
    asyncio.run(main())