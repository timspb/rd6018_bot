# RD6018 Telegram Bot

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![Aiogram](https://img.shields.io/badge/Aiogram-3.x-green.svg)](https://aiogram.dev)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Бот для управления RD6018 через Home Assistant из Telegram:
- авто-режимы заряда Ca/Ca, EFB, AGM;
- ручной режим (Custom);
- график и компактный дашборд в одном сообщении;
- логи этапов и триггеров;
- AI-анализ (опционально, через DeepSeek).

## Что важно знать

- Этапы в авто: `Подготовка -> Main -> (Desulfation) -> Mix -> Безопасное ожидание -> Done`.
- Жесткий лимит тока на всех этапах: **12.0A** (`MAX_STAGE_CURRENT`).
- Защитные лимиты RD6018 при смене этапа: `OVP = U_target + 0.1V`, `OCP = I_target + 0.1A`.
- Защитный лимит Main: `72ч`.
- При тайм-ауте Main для **Ca/Ca** и **EFB** переход в Mix выполняется принудительно.
- Температурная защита по внешнему датчику АКБ: `35C предупреждение`, `40C пауза`, `45C аварийный стоп`.
- `temp_ext` — это температура АКБ, `temp_int` — температура блока/БП; для стратегии и AI ориентируйтесь на [docs/assistant/CHARGE_STRATEGY.md](docs/assistant/CHARGE_STRATEGY.md).

## Профили заряда

### Ca/Ca
- Main: `14.7V`, ток `0.1C` (но не выше 12A)
- Переход Main -> Mix: `CV и I < 0.3A` в течение `3ч` без нового минимума
- Mix: `16.5V`, ток `0.03C` (не выше 12A), лимит `8ч`

### EFB
- Main: `14.8V`, ток `0.1C` (но не выше 12A)
- Переход Main -> Mix: `CV и I < 0.3A` в течение `3ч` без нового минимума
- Mix: `16.5V`, ток `0.03C` (не выше 12A), лимит `10ч`

### AGM
- Main по ступеням: `14.4 -> 14.6 -> 14.8 -> 15.0V`
- Переход между ступенями и в Mix: `CV и I < 0.2A` в течение `2ч` без нового минимума
- Mix: `16.3V`, ток `0.03C` (не выше 12A), лимит `5ч`

## Desulfation (авто)
- Триггер: ток «застрял» в CV не менее 40 минут
- Порог застревания: `>=0.3A` (Ca/Ca, EFB), `>=0.2A` (AGM)
- Уставки: `16.3V` и `2% от Ah` (не выше 12A)
- Лимит: `2ч` на цикл
- Макс циклов: `3` для Ca/Ca/EFB, `4` для AGM

## Custom режим

Пользователь задаёт:
- Main напряжение
- Main ток
- Delta-порог
- Лимит времени Main
- Емкость АКБ (Ah)

Особенности:
- Main стартует сразу, без этапа Подготовка.
- Завершение по delta (dV/dI) или по лимиту времени.
- Для delta используется подтверждение: `3` срабатывания подряд с интервалом `1 мин`.
- Мониторинг delta включается через `120 сек` после смены уставок.

## Команды Telegram

- `/start` — открыть/обновить дашборд
- `/modes` — выбор профиля заряда
- `/off` — меню «Off по условию»
- `/logs` — логи текущей сессии
- `/ai` — AI-анализ телеметрии
- `/stats` — подсказка где смотреть расширенную инфу
- `/entities` — статус HA-сущностей
- `/help` — краткая справка по режимам

## Off по условию

Можно задать выключение по любому из условий:
- напряжение (`V>=`, `V<=`)
- ток (`I>=`, `I<=`)
- таймер (`H:MM`)

Примеры:
- `off I<=1.20`
- `off V>=16.4`
- `off 2:00`
- `off I>=2 V<=13.5 2:00`
- `off` — сброс условия

Состояние сохраняется в `manual_off_state.json` и восстанавливается после перезапуска.

## Дашборд

- Бот поддерживает **одно рабочее сообщение дашборда** на чат/пользователя: обновление идёт через edit/delete, без бесконечного наращивания сообщений.
- Кнопки диапазона графика: `Норма`, `30м`, `2ч`, `Сессия`.
- В «Полная инфо» показываются текущий этап, уставки, лимиты и состояние сессии.
- В «Логи» выводятся события текущей сессии с фильтрацией служебного шума.

## Установка

### Требования
- Python 3.10+
- Home Assistant с интеграцией RD6018
- Telegram bot token
- DeepSeek API key (опционально)

### Быстрый старт

```bash
git clone https://github.com/timspb/rd6018_bot.git
cd rd6018_bot
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell:
# .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python bot.py
```

Перед запуском создайте `.env` в корне проекта.

Пример `.env`:

```env
TG_TOKEN=...
HA_URL=http://homeassistant:8123
HA_TOKEN=...

# Опционально
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
USER_TIMEZONE=Asia/Vladivostok
ALLOWED_CHAT_IDS=
```

## Home Assistant сущности

Имена задаются в `ENTITY_MAP` файла `config.py`.

Ключевые группы:
- телеметрия: напряжение/ток/мощность/Ah/температуры;
- состояние: `switch`, `is_cv`, `is_cc`, `uptime`;
- управление: `set_voltage`, `set_current`, `ovp`, `ocp`.

## Запуск как сервис (systemd)

Пример команд на хосте:

```bash
cd /root/rd6018_bot
git pull
systemctl restart rd6018-bot
systemctl status rd6018-bot --no-pager
journalctl -u rd6018-bot -n 100 --no-pager
```

## Файлы проекта

- `bot.py` — Telegram-бот, интерфейс, команды, дашборд
- `charge_logic.py` — FSM заряда, этапы, триггеры, защиты
- `ai_engine.py` / `ai_system_prompt.py` — AI-аналитика и системный промпт
- `docs/assistant/CHARGE_STRATEGY.md` — краткая опора по этапам, триггерам и температурным сигналам
- `config.py` — env и карта HA-сущностей
- `charging_log.py` — лог событий
- `database.py` — SQLite и данные для графиков
- `graphing.py` — генерация графиков

## Безопасность

- Не запускайте заряд без контроля на длительное время.
- Перед высоковольтными режимами (до 16.5V) отключайте АКБ от бортовой сети авто.
- Используйте внешний датчик температуры АКБ.

## Лицензия

MIT. Использование на ваш риск.

## Assistant Memory

For repeatable work across sessions, these files were added:
- docs/assistant/HISTORY.md - short project history and accepted decisions.
- docs/assistant/INSTRUCTIONS.md - working rules and sync flow.
- docs/assistant/PROMPTS.md - reusable prompt templates.
- docs/assistant/USER_PROMPT_MEMORY.md - ready-to-use prompt to load memory in a new chat.
