# Telegram Research — локальный MCP

Статус: авторизация Telegram API подтверждена; `@zaryadAKBin` доступен; прямой локальный MCP stdio прошел проверку SDK-клиентом.

## Расположение
- Исходники MCP: `telegram_connector/telegram-research-plugin/server.py`
- Манифест: `telegram_connector/telegram-research-plugin/plugin.json`
- MCP конфигурация: `telegram_connector/telegram-research-plugin/mcp.json`
- Изолированная среда: `telegram_connector/.venv/`
- API параметры: `<LOCAL_SECRETS_FILE>` (`api_id`, `api_hash`); значения никогда не выводить
- Telegram сессия: `private/telegram_research.session`; не публиковать, не архивировать в git
- Тест: `telegram_connector/test_mcp.py`

## Реализованные инструменты
1. `recent_messages(limit,before_id)` — только сообщения `@zaryadAKBin`;
2. `search_messages(query,limit)` — поиск по группе;
3. `get_message(message_id)` — чтение конкретного сообщения;
4. `save_research_attachment(message_id)` — выборочная загрузка изображения/документа, типы и размер ограничены.

Отправки сообщений, добавления в чаты, удаления или изменения сообщений нет. Любые дополнительные группы потребуют отдельного разрешения и изменения разрешенного списка.

## Проверка
- Telegram авторизация PASS
- Получение 5 последних сообщений PASS
- MCP protocol initialize и tools/list PASS, 4 инструмента
- `recent_messages(limit=2)` PASS, даты присутствуют
- `search_messages(query='PbSO4',limit=2)` PASS
- Недопустимый ID отклонен PASS

**Граница интеграции:** MCP сервер готов и испытан локальным MCP клиентом, но НЕ добавлен в каталог инструментов текущего ChatGPT чата. Для использования непосредственно как отдельного инструмента ChatGPT потребуется поддерживаемая регистрация локального плагина; сейчас чтение можно осуществлять через HOME-PC MCP. Доступ к токенам и сессии ограничивать на уровне операционной системы; белый список в приложении не является границей полномочий всей Telegram-сессии.