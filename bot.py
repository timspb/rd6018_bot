"""
bot.py — RD6018 Ultimate Telegram Controller (Async Edition).
Дашборд: один автообновляемый message с графиком, метриками и кнопками.
"""
import asyncio
import logging
import re
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
from charge_logic import ChargeController
from config import ENTITY_MAP, HA_URL, HA_TOKEN, MAX_TEMP, TG_TOKEN
from database import add_record, get_graph_data, init_db
from graphing import generate_chart
from hass_api import HassClient

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(name)s - %(message)s",
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
charge_controller = ChargeController(hass)

# Храним message_id дашборда для каждого user_id
user_dashboard: Dict[int, int] = {}
last_chat_id: Optional[int] = None


def _md_to_html(text: str) -> str:
    """Конвертировать **жирный** в <b>жирный</b> для Telegram HTML."""
    if not text:
        return text
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


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
    user_id = msg.from_user.id if msg.from_user else 0

    live = await hass.get_all_live()
    v = _safe_float(live.get("voltage"))
    i = _safe_float(live.get("current"))
    p = _safe_float(live.get("power"))
    ah = _safe_float(live.get("ah"))
    wh = _safe_float(live.get("wh"))
    temp_int = _safe_float(live.get("temp_int"))
    temp_ext = _safe_float(live.get("temp_ext"))
    set_v = _safe_float(live.get("set_voltage"))
    set_i = _safe_float(live.get("set_current"))
    output_state = live.get("switch")
    is_on = str(output_state).lower() == "on"
    is_cv = str(live.get("is_cv", "")).lower() == "on"
    is_cc = str(live.get("is_cc", "")).lower() == "on"
    mode = "CV" if is_cv else ("CC" if is_cc else "-")

    status = "ВКЛ" if is_on else "ВЫКЛ"
    text = (
        "<b>📊 СТАТУС:</b> {} | {}\n"
        "<b>⚡ LIVE:</b> {:.2f}В | {:.2f}А | {:.2f}Вт\n"
        "<b>🎯 ЦЕЛЬ:</b> {:.2f}В | {:.1f}А\n"
        "<b>🔋 ЕМКОСТЬ:</b> {:.2f} Ач | {:.1f} Втч\n"
        "<b>🌡 ТЕМП:</b> {:.1f}°C (Внеш) | {:.1f}°C (Внутр)"
    ).format(status, mode, v, i, p, set_v, set_i, ah, wh, temp_ext, temp_int)

    times, voltages, currents = await get_graph_data(limit=100)
    buf = generate_chart(times, voltages, currents)
    photo = BufferedInputFile(buf.getvalue(), filename="chart.png") if buf else None

    ikb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh"),
                InlineKeyboardButton(text="🔋 Пресеты", callback_data="presets"),
            ],
            [
                InlineKeyboardButton(text="📈 Логи", callback_data="logs"),
                InlineKeyboardButton(text="🧠 AI Анализ", callback_data="ai_analysis"),
            ],
            [
                InlineKeyboardButton(
                    text="🛑 ВЫКЛ" if is_on else "⚡ ВКЛ",
                    callback_data="power_toggle",
                )
            ],
        ]
    )

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


async def data_logger() -> None:
    """Фоновая задача: опрос HA каждые 30с, сохранение в DB, проверка безопасности."""
    global last_chat_id
    while True:
        try:
            live = await hass.get_all_live()
            v = _safe_float(live.get("voltage"))
            i = _safe_float(live.get("current"))
            p = _safe_float(live.get("power"))
            temp_ext = live.get("temp_ext")
            t = _safe_float(temp_ext)
            await add_record(v, i, p, t)

            if temp_ext is not None and float(temp_ext) > MAX_TEMP:
                await hass.turn_off(ENTITY_MAP["switch"])
                alert = (
                    f"🚨 КРИТИЧЕСКИЙ ПЕРЕГРЕВ АКБ! T={float(temp_ext):.1f}°C. "
                    "ПИТАНИЕ ОТКЛЮЧЕНО!"
                )
                logger.warning(alert)
                if last_chat_id:
                    try:
                        await bot.send_message(last_chat_id, alert, parse_mode=ParseMode.HTML)
                    except Exception:
                        pass
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


@router.callback_query(F.data == "presets")
async def presets_menu(call: CallbackQuery) -> None:
    ikb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="AGM (14.4V)", callback_data="preset_agm"),
                InlineKeyboardButton(text="GEL (14.2V)", callback_data="preset_gel"),
            ],
            [InlineKeyboardButton(text="Repair (14.8V)", callback_data="preset_repair")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="refresh")],
        ]
    )
    await call.message.edit_caption(caption="<b>Выберите пресет:</b>", reply_markup=ikb)
    await call.answer()


@router.callback_query(F.data.in_({"preset_agm", "preset_gel", "preset_repair"}))
async def preset_selection(call: CallbackQuery) -> None:
    mapping = {"preset_agm": 14.4, "preset_gel": 14.2, "preset_repair": 14.8}
    v = mapping.get(call.data, 14.4)
    await hass.set_voltage(v)
    await call.answer(f"Установлено {v}V")
    old_id = user_dashboard.get(call.from_user.id) if call.from_user else None
    await send_dashboard(call, old_msg_id=old_id)


@router.callback_query(F.data == "logs")
async def logs_handler(call: CallbackQuery) -> None:
    times, voltages, currents = await get_graph_data(limit=5)
    if not times:
        text = "Нет данных."
    else:
        lines = []
        for j in range(min(5, len(times))):
            lines.append(f"{times[j]}: U={voltages[j]:.2f}В I={currents[j]:.2f}А")
        text = "<b>Последние логи:</b>\n" + "\n".join(lines)
    await call.message.answer(text, parse_mode=ParseMode.HTML)
    await call.answer()


@router.callback_query(F.data == "ai_analysis")
async def ai_analysis_handler(call: CallbackQuery) -> None:
    await call.answer()
    status_msg = await call.message.answer("⏳ Анализирую...", parse_mode=ParseMode.HTML)
    times, voltages, currents = await get_graph_data(limit=100)
    history = {"times": times, "voltages": voltages, "currents": currents}
    result = await ask_deepseek(history)
    result_html = _md_to_html(result)
    await status_msg.edit_text(f"<b>🧠 AI Анализ:</b>\n{result_html}", parse_mode=ParseMode.HTML)


async def main() -> None:
    await init_db()
    dp.include_router(router)
    await bot.set_my_commands([BotCommand(command="start", description="Открыть дашборд RD6018")])
    asyncio.create_task(data_logger())
    logger.info("RD6018 bot starting")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
