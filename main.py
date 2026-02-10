import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from database import Database
from config import HA_URL, HA_TOKEN, ENTITY_IDS
from hass_api import HassAPI
from charge_logic import ChargeController
import logging

TOKEN = 'your-telegram-bot-token'

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)
db = Database()
hass = HassAPI(HA_URL, HA_TOKEN)
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

@dp.message_handler(commands=['start_charge'])
async def start_charge(message: types.Message):
    logging.info('Команда /start_charge получена')
    await message.reply('Выберите тип АКБ (Ca/Ca, EFB, AGM) и емкость (Ah):')
    # ...логика выбора типа и запуска сессии...

@dp.message_handler(commands=['status'])
async def status(message: types.Message):
    logging.info('Команда /status получена')
    session = db.get_last_session()
    if session:
        state = session[3]
        v_max = session[6]
        i_min = session[7]
        await message.reply(f'Текущий этап: {state}\nV_max: {v_max}\nI_min: {i_min}')
    else:
        await message.reply('Нет активной сессии.')

@dp.message_handler(commands=['stop'])
async def stop(message: types.Message):
    logging.info('Команда /stop получена')
    await hass.turn_off_switch(ENTITY_IDS['output_switch'])
    db.log(db.get_last_session()[0], 'Экстренное выключение выхода по команде /stop')
    await message.reply('Выход RD6018 выключен.')

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
