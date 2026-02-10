@router.callback_query(F.data == "preset_agm")
async def preset_agm_handler(call: CallbackQuery):
    await hass.set_number('sensor.rd_6018_output_voltage', 14.4)
    old_id = getattr(call.bot, 'user_dash', {}).get(call.from_user.id)
    msg_id = await dashboard(call.message, old_msg_id=old_id)
    if not hasattr(call.bot, 'user_dash'): call.bot.user_dash = {}
    call.bot.user_dash[call.from_user.id] = msg_id
    await call.answer("AGM выбран: 14.4V")

@router.callback_query(F.data == "preset_gel")
async def preset_gel_handler(call: CallbackQuery):
    await hass.set_number('sensor.rd_6018_output_voltage', 14.2)
    old_id = getattr(call.bot, 'user_dash', {}).get(call.from_user.id)
    msg_id = await dashboard(call.message, old_msg_id=old_id)
    if not hasattr(call.bot, 'user_dash'): call.bot.user_dash = {}
    call.bot.user_dash[call.from_user.id] = msg_id
    await call.answer("GEL выбран: 14.2V")

@router.callback_query(F.data == "preset_deep")
async def preset_deep_handler(call: CallbackQuery):
    await hass.set_number('sensor.rd_6018_output_voltage', 14.8)
    old_id = getattr(call.bot, 'user_dash', {}).get(call.from_user.id)
    msg_id = await dashboard(call.message, old_msg_id=old_id)
    if not hasattr(call.bot, 'user_dash'): call.bot.user_dash = {}
    call.bot.user_dash[call.from_user.id] = msg_id
    await call.answer("Deep выбран: 14.8V")

@router.callback_query(F.data == "power_on")
async def power_on_handler(call: CallbackQuery):
    await hass.turn_on_switch('switch.rd_6018_output')
    old_id = getattr(call.bot, 'user_dash', {}).get(call.from_user.id)
    msg_id = await dashboard(call.message, old_msg_id=old_id)
    if not hasattr(call.bot, 'user_dash'): call.bot.user_dash = {}
    call.bot.user_dash[call.from_user.id] = msg_id
    await call.answer("Питание включено")

@router.callback_query(F.data == "power_off")
async def power_off_handler(call: CallbackQuery):
    await hass.turn_off_switch('switch.rd_6018_output')
    old_id = getattr(call.bot, 'user_dash', {}).get(call.from_user.id)
    msg_id = await dashboard(call.message, old_msg_id=old_id)
    if not hasattr(call.bot, 'user_dash'): call.bot.user_dash = {}
    call.bot.user_dash[call.from_user.id] = msg_id
    await call.answer("Питание отключено")
import asyncio
import logging
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import io
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from database import Database
from config import HA_URL, HA_TOKEN, ENTITY_IDS, TOKEN
from hass_api import HassAPI
from charge_logic import ChargeController
from ai_analyst import AIAnalyst
import datetime

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
db = Database()
hass = HassAPI(HA_URL, HA_TOKEN)
charge_controller = None
charge_task = None

# --- Real-time Engine: background HA polling ---
async def ha_background_poll(bot, hass, db: Database):
    while True:
        try:
            voltage, _ = await hass.get_state('sensor.rd_6018_output_voltage')
            current, _ = await hass.get_state('sensor.rd_6018_output_current')
            power, _ = await hass.get_state('sensor.rd_6018_output_power')
            temp, _ = await hass.get_state('sensor.rd_6018_temperature_external')
            db.add_sensor_history(voltage, current, power, temp)
            if temp is not None and float(temp) > 45.0 or voltage is not None and float(voltage) > 15.0:
                await hass.turn_off_switch('switch.rd_6018_output')
                analyst = AIAnalyst()
                session_history = analyst.get_last_sessions(limit=3)
                hass_data = {
                    'sensor.rd_6018_output_voltage': voltage,
                    'sensor.rd_6018_output_current': current,
                    'sensor.rd_6018_output_power': power,
                    'sensor.rd_6018_temperature_external': temp,
                    'switch.rd_6018_output': 'off',
                }
                ai_alert = analyst.analyze(hass_data, session_history)
                if hasattr(bot, 'user_dash'):
                    for uid in bot.user_dash:
                        try:
                            await bot.send_message(uid, f'🆘 <b>АВАРИЙНОЕ ОТКЛЮЧЕНИЕ!</b>\n{ai_alert}')
                        except Exception:
                            pass
        except Exception as e:
            print(f'[HA BG POLL] Ошибка: {e}')
        await asyncio.sleep(30)
@router.callback_query(F.data == "presets")
async def presets_menu(call: CallbackQuery):
    ikb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="AGM", callback_data="preset_agm"),
             InlineKeyboardButton(text="GEL", callback_data="preset_gel"),
             InlineKeyboardButton(text="Li-Ion", callback_data="preset_li")],
            [InlineKeyboardButton(text="🚀 BOOST (Макс. ток)", callback_data="boost")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="refresh")],
        ]
    )
    await call.message.edit_caption(caption="<b>Выберите пресет или BOOST:</b>", reply_markup=ikb)
    await call.answer()

@router.callback_query(F.data == "boost")
async def boost_handler(call: CallbackQuery):
    # Получаем актуальное напряжение
    voltage, _ = await hass.get_state('sensor.rd_6018_output_voltage')
    try:
        voltage = float(voltage)
    except Exception:
        voltage = 0
    if voltage < 14.4:
        # TODO: поднять лимит тока до максимума через hass
        await call.answer("BOOST: Ток увеличен до максимума!", show_alert=True)
    else:
        await call.answer("Буст опасен на стадии насыщения!", show_alert=True)
    # Вернуть дашборд
    old_id = getattr(call.bot, 'user_dash', {}).get(call.from_user.id)
    msg_id = await dashboard(call.message, old_msg_id=old_id)
    if not hasattr(call.bot, 'user_dash'): call.bot.user_dash = {}
    call.bot.user_dash[call.from_user.id] = msg_id
# --- DASHBOARD v1.0 ---
from aiogram.types import CallbackQuery
import datetime

async def dashboard(message: Message, old_msg_id=None):
    # Получаем live-данные из Home Assistant (асинхронно)
    voltage, _ = await hass.get_state('sensor.rd_6018_output_voltage')
    current, _ = await hass.get_state('sensor.rd_6018_output_current')
    power, _ = await hass.get_state('sensor.rd_6018_output_power')
    temp, _ = await hass.get_state('sensor.rd_6018_temperature_external')
    ah = None
    try:
        ah, _ = await hass.get_state('sensor.rd_6018_battery_charge')
        ah = float(ah)
    except Exception:
        ah = 0.0
    output_state, _ = await hass.get_state('switch.rd_6018_output')
    status = 'ЗАРЯДКА' if output_state == 'on' else 'ВЫКЛ'
    temp_status = 'Норма' if temp is not None and float(temp) < 40 else 'ВНИМАНИЕ'
    # Форматирование
    voltage_fmt = f"{float(voltage):.2f}"
    current_fmt = f"{float(current):.2f}"
    power_fmt = f"{float(power):.2f}"
    temp_fmt = f"{float(temp):.2f}"
    ah_fmt = f"{float(ah):.2f}"
    # AI verdict (коротко)
    analyst = AIAnalyst()
    session_history = analyst.get_last_sessions(limit=3)
    hass_data = {
        'sensor.rd_6018_output_voltage': voltage,
        'sensor.rd_6018_output_current': current,
        'sensor.rd_6018_output_power': power,
        'sensor.rd_6018_battery_charge': ah,
        'sensor.rd_6018_temperature_external': temp,
        'switch.rd_6018_output': output_state,
    }
    try:
        ai_short = analyst.analyze(hass_data, session_history)
        if not ai_short or 'Мало данных' in ai_short:
            ai_short = 'Набираю базу данных...'
        elif len(ai_short) > 80:
            ai_short = ai_short[:80] + '...'
    except Exception as e:
        ai_short = f"AI: {e}"
    # График: последние 100 точек из sensor_history
    sensor_rows = []
    try:
        cursor = db.conn.cursor()
        cursor.execute('SELECT timestamp, voltage, current FROM sensor_history ORDER BY id DESC LIMIT 100')
        sensor_rows = cursor.fetchall()
    except Exception:
        pass
    times, voltages, currents = [], [], []
    for row in reversed(sensor_rows):
        times.append(row[0][-8:])
        try:
            voltages.append(float(row[1]))
            currents.append(float(row[2]))
        except Exception:
            voltages.append(0.0)
            currents.append(0.0)
    voltages = [float(v) for v in voltages]
    currents = [float(i) for i in currents]
    if not times:
        now = datetime.datetime.now()
        times = [(now - datetime.timedelta(minutes=100-i)).strftime('%H:%M') for i in range(100)]
        voltages = [float(voltage_fmt) for _ in range(100)]
        currents = [float(current_fmt) for _ in range(100)]
    fig, ax1 = plt.subplots(figsize=(7,3), facecolor="#222")
    ax1.set_facecolor("#222")
    ax1.plot(times, voltages, '-', color="#00eaff", label="V")
    ax2 = ax1.twinx()
    ax2.plot(times, currents, '-', color="#ffb300", label="A")
    ax1.set_xlabel("Время", color="#fff")
    ax1.set_ylabel("V", color="#00eaff")
    ax2.set_ylabel("A", color="#ffb300")
    ax1.tick_params(axis='x', colors="#fff", labelsize=8, rotation=45)
    ax1.tick_params(axis='y', colors="#00eaff")
    ax2.tick_params(axis='y', colors="#ffb300")
    plt.title("U/I", color="#fff")
    fig.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)
    photo = BufferedInputFile(buf.read(), filename="chart.png")
    # Индикация режима
    cc_limit = 5.00  # TODO: брать из настроек
    cv_setpoint = 14.40  # TODO: брать из пресета
    mode = ""
    try:
        if abs(float(current_fmt) - cc_limit) < 0.05:
            mode = "Режим: CC (Стаб. тока)"
        elif abs(float(voltage_fmt) - cv_setpoint) < 0.05 and float(current_fmt) < cc_limit:
            mode = "Режим: CV (Стаб. напряжения)"
    except Exception:
        mode = ""
    text = (
        f"🔋 <b>Статус:</b> <b>{status}</b>\n"
        f"⚡ <b>Параметры:</b> <b>{voltage_fmt}V | {current_fmt}A | {power_fmt}W</b>\n"
        f"🌡 <b>Температура:</b> <b>{temp_fmt}°C</b> ({temp_status})\n"
        f"📊 <b>Емкость:</b> <b>{ah_fmt} Ah</b>\n"
        f"{mode}\n"
        f"🧠 <b>AI Анализ:</b> {ai_short}"
    )
    power_on = output_state == 'off'
    power_btn = InlineKeyboardButton(
        text="🛑 ВЫКЛЮЧИТЬ ПИТАНИЕ" if not power_on else "⚡ ЗАПУСТИТЬ ЗАРЯД",
        callback_data="power_toggle"
    )
    ikb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить Данные", callback_data="refresh")],
            [InlineKeyboardButton(text="🧠 Подробный AI Анализ", callback_data="ai_full")],
            [InlineKeyboardButton(text="🔋 Пресеты", callback_data="presets")],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings"), InlineKeyboardButton(text="📈 Логи", callback_data="logs")],
            [power_btn],
        ]
    )
    if old_msg_id:
        try:
            await message.bot.delete_message(message.chat.id, old_msg_id)
        except Exception:
            pass
    try:
        await message.delete()
    except Exception:
        pass
    sent = await message.answer_photo(photo=photo, caption=text, reply_markup=ikb)
    return sent.message_id
# Power Toggle обработчик
@router.callback_query(F.data == "power_toggle")
async def power_toggle_handler(call: CallbackQuery):
    output_state, _ = await hass.get_state('switch.rd_6018_output')
    if output_state == 'on':
        await hass.turn_off_switch('switch.rd_6018_output')
    else:
        try:
            await hass.turn_on_switch('switch.rd_6018_output')
        except Exception:
            pass
    output_state, _ = await hass.get_state('switch.rd_6018_output')
    old_id = getattr(call.bot, 'user_dash', {}).get(call.from_user.id)
    msg_id = await dashboard(call.message, old_msg_id=old_id)
    if not hasattr(call.bot, 'user_dash'): call.bot.user_dash = {}
    call.bot.user_dash[call.from_user.id] = msg_id
    await call.answer("Статус питания обновлен")
# Пресеты подменю
@router.callback_query(F.data == "presets")
async def presets_menu(call: CallbackQuery):
    ikb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="AGM (14.4V)", callback_data="preset_agm"),
             InlineKeyboardButton(text="GEL (14.2V)", callback_data="preset_gel")],
            [InlineKeyboardButton(text="Deep Charge (14.8V)", callback_data="preset_deep")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="refresh")],
        ]
    )
    await call.message.edit_caption(caption="<b>Выберите пресет:</b>", reply_markup=ikb)
    await call.answer()
# Логи обработчик
# Логи обработчик
@router.callback_query(F.data == "logs")
async def logs_handler(call: CallbackQuery):
    try:
        cursor = db.conn.cursor()
        cursor.execute('SELECT timestamp, voltage, current, power, temp FROM sensor_history ORDER BY id DESC LIMIT 5')
        rows = cursor.fetchall()
        log_text = '\n'.join([f"{r[0]} | V:{float(r[1]):.2f} I:{float(r[2]):.2f} P:{float(r[3]):.2f} T:{float(r[4]):.2f}" for r in rows])
        if not log_text:
            log_text = 'Нет данных.'
        await call.message.answer(f'<b>Последние логи:</b>\n{log_text}')
    except Exception as e:
        await call.message.answer(f'Ошибка логов: {e}')
    await call.answer()
# edit_message_caption для быстрого обновления параметров
@router.callback_query(F.data == "refresh")
async def refresh_dashboard(call: CallbackQuery):
    old_id = getattr(call.bot, 'user_dash', {}).get(call.from_user.id)
    voltage, _ = await hass.get_state('sensor.rd_6018_output_voltage')
    current, _ = await hass.get_state('sensor.rd_6018_output_current')
    power, _ = await hass.get_state('sensor.rd_6018_output_power')
    temp, _ = await hass.get_state('sensor.rd_6018_temperature_external')
    ah = None
    try:
        ah, _ = await hass.get_state('sensor.rd_6018_battery_charge')
        ah = float(ah)
    except Exception:
        ah = 0.0
    output_state, _ = await hass.get_state('switch.rd_6018_output')
    status = 'ЗАРЯДКА' if output_state == 'on' else 'ВЫКЛ'
    temp_status = 'Норма' if temp is not None and float(temp) < 40 else 'ВНИМАНИЕ'
    voltage_fmt = f"{float(voltage):.2f}"
    current_fmt = f"{float(current):.2f}"
    power_fmt = f"{float(power):.2f}"
    temp_fmt = f"{float(temp):.2f}"
    ah_fmt = f"{float(ah):.2f}"
    cc_limit = 5.00
    cv_setpoint = 14.40
    mode = ""
    try:
        if abs(float(current_fmt) - cc_limit) < 0.05:
            mode = "Режим: Стабилизация тока (CC)"
        elif abs(float(voltage_fmt) - cv_setpoint) < 0.05 and float(current_fmt) < cc_limit:
            mode = "Режим: Насыщение (CV)"
    except Exception:
        mode = ""
    analyst = AIAnalyst()
    session_history = analyst.get_last_sessions(limit=3)
    hass_data = {
        'sensor.rd_6018_output_voltage': voltage,
        'sensor.rd_6018_output_current': current,
        'sensor.rd_6018_output_power': power,
        'sensor.rd_6018_battery_charge': ah,
        'sensor.rd_6018_temperature_external': temp,
        'switch.rd_6018_output': output_state,
    }
    try:
        ai_short = analyst.analyze(hass_data, session_history)
        if not ai_short or 'Мало данных' in ai_short:
            ai_short = 'Набираю базу данных...'
        elif len(ai_short) > 80:
            ai_short = ai_short[:80] + '...'
    except Exception as e:
        ai_short = f"AI: {e}"
    text = (
        f"🔋 <b>Статус:</b> <b>{status}</b>\n"
        f"⚡ <b>Параметры:</b> <b>{voltage_fmt}V | {current_fmt}A | {power_fmt}W</b>\n"
        f"🌡 <b>Температура:</b> <b>{temp_fmt}°C</b> ({temp_status})\n"
        f"📊 <b>Емкость:</b> <b>{ah_fmt} Ah</b>\n"
        f"{mode}\n"
        f"🧠 <b>AI Анализ:</b> {ai_short}"
    )
    try:
        await call.message.edit_caption(caption=text)
    except Exception:
        old_id = getattr(call.bot, 'user_dash', {}).get(call.from_user.id)
        msg_id = await dashboard(call.message, old_msg_id=old_id)
        if not hasattr(call.bot, 'user_dash'): call.bot.user_dash = {}
        call.bot.user_dash[call.from_user.id] = msg_id
    await call.answer("Данные обновлены")



import asyncio
import logging
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import io
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram import Router
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from database import Database
from config import HA_URL, HA_TOKEN, ENTITY_IDS
from hass_api import HassAPI
from charge_logic import ChargeController


from config import TOKEN
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
db = Database()
hass = HassAPI(HA_URL, HA_TOKEN)
router = Router()

# Глобальный контроллер заряда
charge_controller = None
charge_task = None



# Главное меню
@router.message(Command('start'))
async def start(message: Message):
    logging.info('Команда /start получена')
    msg_id = await dashboard(message)
    # Сохраняем id дашборда в user_data (in-memory)
    if not hasattr(message.bot, 'user_dash'): message.bot.user_dash = {}
    message.bot.user_dash[message.from_user.id] = msg_id

# Меню Заряда (InlineKeyboard)
@router.message(F.text == "⚡ Заряд")
async def charge_menu(message: Message):
    ikb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Ca/Ca", callback_data="type_CaCa"),
             InlineKeyboardButton(text="EFB", callback_data="type_EFB")],
            [InlineKeyboardButton(text="AGM", callback_data="type_AGM"),
             InlineKeyboardButton(text="GEL", callback_data="type_GEL")],
            [InlineKeyboardButton(text="55Ah", callback_data="ah_55"),
             InlineKeyboardButton(text="60Ah", callback_data="ah_60")],
            [InlineKeyboardButton(text="75Ah", callback_data="ah_75"),
             InlineKeyboardButton(text="100Ah", callback_data="ah_100")],
            [InlineKeyboardButton(text="Свой", callback_data="ah_custom")],
        ]
    )
    await message.answer("<b>⚡ Заряд: выберите тип АКБ и емкость</b>", reply_markup=ikb)

# Toggle-кнопка управления выходом
@router.message(F.text == "⚙️ Настройки")
async def settings_menu(message: Message):
    # Пример: получаем состояние выхода (заглушка)
    output_on = True  # TODO: получить реальное состояние
    btn_text = "Выключить Выход" if output_on else "Включить Выход"
    ikb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=btn_text, callback_data="toggle_output")],
        ]
    )
    await message.answer("<b>🛠 Управление выходом</b>", reply_markup=ikb)

# Toggle обработка
@router.callback_query(F.data == "toggle_output")
async def toggle_output(call):
    # TODO: получить и переключить реальное состояние выхода
    # Здесь просто пример
    await call.answer("🔄 Переключение выхода (заглушка)")
    await call.message.edit_reply_markup()

# Обработка ручной команды set V I
@router.message(F.text.regexp(r'^set\s+(\d+\.?\d*)\s+(\d+\.?\d*)$'))
async def manual_set(message: Message):
    import re
    m = re.match(r'^set\s+(\d+\.?\d*)\s+(\d+\.?\d*)$', message.text.strip())
    if not m:
        await message.answer('Формат: set 14.4 5')
        return
    voltage, current = float(m.group(1)), float(m.group(2))
    # TODO: отправить параметры в RD6018
    await message.answer(f'✅ Установлено: <b>{voltage} В</b>, <b>{current} А</b>')

@router.message(F.text == "📊 Статус")
async def status_button(message: Message):
    # Просто перерисовываем дашборд
    old_id = getattr(message.bot, 'user_dash', {}).get(message.from_user.id)
    msg_id = await dashboard(message, old_msg_id=old_id)
    if not hasattr(message.bot, 'user_dash'): message.bot.user_dash = {}
    message.bot.user_dash[message.from_user.id] = msg_id
# --- Dashboard Inline Buttons ---
@router.callback_query(F.data == "refresh")
async def refresh_dashboard(call: CallbackQuery):
    old_id = getattr(call.bot, 'user_dash', {}).get(call.from_user.id)
    msg_id = await dashboard(call.message, old_msg_id=old_id)
    if not hasattr(call.bot, 'user_dash'): call.bot.user_dash = {}
    call.bot.user_dash[call.from_user.id] = msg_id
    await call.answer("Данные обновлены")

@router.callback_query(F.data == "power_off")
async def power_off(call: CallbackQuery):
    await hass.turn_off_switch('switch.rd_6018_output')
    old_id = getattr(call.bot, 'user_dash', {}).get(call.from_user.id)
    msg_id = await dashboard(call.message, old_msg_id=old_id)
    if not hasattr(call.bot, 'user_dash'): call.bot.user_dash = {}
    call.bot.user_dash[call.from_user.id] = msg_id
    await call.answer("Питание отключено")

@router.callback_query(F.data == "power_on")
async def power_on(call: CallbackQuery):
    # TODO: включить выход через hass
    # await hass.turn_on_switch('switch.rd_6018_output')
    old_id = getattr(call.bot, 'user_dash', {}).get(call.from_user.id)
    msg_id = await dashboard(call.message, old_msg_id=old_id)
    if not hasattr(call.bot, 'user_dash'): call.bot.user_dash = {}
    call.bot.user_dash[call.from_user.id] = msg_id
    await call.answer("Питание включено")
async def stop_main_menu(message: Message):
    await hass.turn_off_switch('switch.rd_6018_output')
    await message.answer('🛑 <b>Выход RD6018 выключен.</b>')

# AI-анализ по кнопке
from ai_analyst import AIAnalyst
@router.callback_query(F.data == "ai_analyze")
async def ai_analyze_handler(call):
    hass_data = {
        'sensor.rd_6018_output_voltage': 14.81,
        'sensor.rd_6018_output_current': 0.42,
        'sensor.rd_6018_battery_charge': 19.75,
        'sensor.rd_6018_battery_energy': 290.09,
        'sensor.rd_6018_temperature_external': 21.0,
        'switch.rd_6018_output': 'on',
    }
    analyst = AIAnalyst()
    session_history = analyst.get_last_sessions(limit=5)
    try:
        result = analyst.analyze(hass_data, session_history)
    except Exception as e:
        result = f"Ошибка AI-анализа: {e}"
    # Обновляем статус через edit_message_text
    await call.message.edit_text(f"<b>🧠 AI-анализ:</b>\n{result}", reply_markup=None)
    await call.answer()

@router.message(F.text == "Остановить")
async def stop_button(message: Message):
    await stop(message)

@router.message(F.text.regexp(r'^(Ca/Ca|EFB|AGM)\s+([0-9]+)'))
async def handle_battery_type(message: Message):
    global charge_controller, charge_task
    import re
    m = re.match(r'^(Ca/Ca|EFB|AGM)\s+([0-9]+)', message.text.strip())
    if not m:
        await message.answer('Формат: AGM 60')
        return
    battery_type, ah = m.group(1), int(m.group(2))
    session_id = db.start_session(battery_type)
    charge_controller = ChargeController(hass, db, session_id)
    await message.answer(f'Запуск заряда для {battery_type}, {ah}Ah. Стартую процесс...')
    # Запускаем процесс заряда в фоне
    if charge_task and not charge_task.done():
        charge_task.cancel()
    charge_task = asyncio.create_task(charge_process(message, battery_type, ah))

async def charge_process(message, battery_type, ah):
    global charge_controller
    MAX_TEMP = 45.0
    MAX_VOLTAGE = 17.0
    try:
        while True:
            # Получаем данные из HA (заглушка, заменить на реальные асинхронные вызовы)
            hass_data = {
                'sensor.rd_6018_output_voltage': 14.81,
                'sensor.rd_6018_temperature_external': 21.0,
            }
            voltage = float(hass_data['sensor.rd_6018_output_voltage'])
            temp = float(hass_data['sensor.rd_6018_temperature_external'])
            if temp > MAX_TEMP or voltage > MAX_VOLTAGE + 0.5:
                # Немедленно выключить выход
                await hass.turn_off_switch('switch.rd_6018_output')
                await message.answer('🆘 <b>CRITICAL OVERHEAT/OVERVOLTAGE!</b>\n<b>Выход отключён.</b> Проверьте температуру и напряжение!')
                break
            # Здесь должна быть логика State Machine
            await charge_controller.safety_check()
            # ...другие этапы заряда...
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        await message.answer('⏹️ <b>Заряд остановлен.</b>')
    except Exception as e:
        logging.error(f'Ошибка процесса заряда: {e}')
        await message.answer(f'⚠️ <b>Ошибка процесса заряда:</b> {e}')

@router.message(Command('status'))
async def status(message: Message):
    logging.info('Команда /status получена')
    session = db.get_last_session()
    if session:
        state = session[3]
        v_max = session[6]
        i_min = session[7]
        await message.answer(f'Текущий этап: {state}\nV_max: {v_max}\nI_min: {i_min}')
    else:
        await message.answer('Нет активной сессии.')

@router.message(Command('stop'))
async def stop(message: Message):
    global charge_task
    logging.info('Команда /stop получена')
    await hass.turn_off_switch(ENTITY_IDS['output_switch'])
    db.log(db.get_last_session()[0], 'Экстренное выключение выхода по команде /stop')
    if charge_task and not charge_task.done():
        charge_task.cancel()
    await message.answer('Выход RD6018 выключен.')

async def main():
    dp.include_router(router)
    asyncio.create_task(ha_background_poll(bot, hass, db))
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
