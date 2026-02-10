


import asyncio
import logging
from aiogram import Bot, Dispatcher, F, DefaultBotProperties
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ParseMode
from database import Database
from config import HA_URL, HA_TOKEN, ENTITY_IDS
from config import TOKEN
from hass_api import HassAPI
from charge_logic import ChargeController


TOKEN = 'your-telegram-bot-token'
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
db = Database()
hass = HassAPI(HA_URL, HA_TOKEN)

# Глобальный контроллер заряда
charge_controller = None
charge_task = None

@dp.message(Command('start_charge'))
async def start_charge(message: Message):
    logging.info('Команда /start_charge получена')
    await message.answer('Выберите тип АКБ (Ca/Ca, EFB, AGM) и емкость (Ah):')
    # Для простоты: ждем ответ пользователя одной строкой "AGM 60"
    # В реальном боте лучше FSM, но здесь — просто

@dp.message(F.text.regexp(r'^(Ca/Ca|EFB|AGM)\s+([0-9]+)'))
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
    # Пример простого цикла опроса
    try:
        while True:
            # Здесь должна быть логика State Machine
            await charge_controller.safety_check()
            # ...другие этапы заряда...
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        await message.answer('Заряд остановлен.')
    except Exception as e:
        logging.error(f'Ошибка процесса заряда: {e}')
        await message.answer(f'Ошибка процесса заряда: {e}')

@dp.message(Command('status'))
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

@dp.message(Command('stop'))
async def stop(message: Message):
    global charge_task
    logging.info('Команда /stop получена')
    await hass.turn_off_switch(ENTITY_IDS['output_switch'])
    db.log(db.get_last_session()[0], 'Экстренное выключение выхода по команде /stop')
    if charge_task and not charge_task.done():
        charge_task.cancel()
    await message.answer('Выход RD6018 выключен.')

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
