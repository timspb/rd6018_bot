


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
    # Получаем параметры (заглушка, заменить на реальные)
    hass_data = {
        'sensor.rd_6018_output_voltage': 14.81,
        'sensor.rd_6018_output_current': 0.42,
        'sensor.rd_6018_temperature_external': 21.0,
        'switch.rd_6018_output': 'on',
    }
    voltage = hass_data['sensor.rd_6018_output_voltage']
    current = hass_data['sensor.rd_6018_output_current']
    temp = hass_data['sensor.rd_6018_temperature_external']
    output_status = 'Включен' if hass_data['switch.rd_6018_output'] == 'on' else 'Выключен'
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Статус"), KeyboardButton(text="⚡ Заряд")],
            [KeyboardButton(text="🛑 СТОП (Выкл)")],
            [KeyboardButton(text="⚙️ Настройки")],
        ],
        resize_keyboard=True
    )
    text = (
        f"<b>🔌 RD6018 Charger Bot</b>\n"
        f"<b>Напряжение:</b> <b>{voltage} В</b>\n"
        f"<b>Ток:</b> <b>{current} А</b>\n"
        f"<b>Температура:</b> <b>{temp}°C</b>\n"
        f"<b>Статус выхода:</b> <b>{output_status}</b>\n"
        "\nВыберите действие:"
    )
    await message.answer(text, reply_markup=kb)

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
    ikb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧠 Анализ AI", callback_data="ai_analyze")],
        ]
    )
    hass_data = {
        'sensor.rd_6018_output_voltage': 14.81,
        'sensor.rd_6018_output_current': 0.42,
        'sensor.rd_6018_battery_charge': 19.75,
        'sensor.rd_6018_battery_energy': 290.09,
        'sensor.rd_6018_temperature_external': 21.0,
        'switch.rd_6018_output': 'on',
    }
    ah = hass_data['sensor.rd_6018_battery_charge']
    wh = hass_data['sensor.rd_6018_battery_energy']
    voltage = hass_data['sensor.rd_6018_output_voltage']
    current = hass_data['sensor.rd_6018_output_current']
    temp = hass_data['sensor.rd_6018_temperature_external']
    output_status = 'Включен' if hass_data['switch.rd_6018_output'] == 'on' else 'Выключен'
    text = (
        f"<b>📊 Статус</b>\n"
        f"<b>Напряжение:</b> <b>{voltage} В</b>\n"
        f"<b>Ток:</b> <b>{current} А</b>\n"
        f"<b>Температура:</b> <b>{temp}°C</b>\n"
        f"<b>Статус выхода:</b> <b>{output_status}</b>\n"
        f"🔋 <b>{ah:.2f} Ah</b>  ⚡ <b>{wh:.2f} Wh</b>"
    )
    sent = await message.answer(text, reply_markup=ikb)
    # Сохраняем id для edit_message_text
    message.bot_status_id = sent.message_id
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
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
