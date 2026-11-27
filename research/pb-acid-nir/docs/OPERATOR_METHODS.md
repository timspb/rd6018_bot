# OPERATOR_METHODS — инструментальные приёмы и научная методика
Актуально 28.11.2026. Использовать совместно с RUNBOOK.md, ROADMAP.md, HANDOFF_NEW_CHAT.md.

## Среда и инструменты
Основной каталог HOME-PC: <RESEARCH_ROOT>; WSL: /mnt/e/CODEX/Pb-Research. Операционная система Windows, научные скрипты Python в tools/, Telegram-процессы в telegram_connector/. Никаких операций вне данного проекта, особенно RD6018, ESP, node104, БВ-600, без отдельного поручения.

В ChatGPT доступ к HOME-PC осуществляется через functions.exec. Сначала искать актуальные инструменты в ALL_TOOLS (фильтр имён mcp__mcp_gateway_home_pc__), затем вызывать tools.mcp__mcp_gateway_home_pc__... внутри functions.exec. Нельзя говорить «HOME-PC недоступен» без реальной проверки.
Проверенные интерфейсы:
- read_file: path (полный Windows-путь), offset, length; offset=-N означает хвост N строк, для PDF offset=номер страницы (нумерация с 0). Результат может иметь поле text или content, а у PDF изображения в content_items. Сканированные таблицы проверять визуально.
- list_directory: path, depth — сверить наличие файлов и структур.
- write_file: path, content, mode rewrite или append. Новые отчёты — rewrite; регистры и исторический checkpoint — append.
- edit_block: file_path, old_string, new_string, expected_replacements:1. Проверить замену чтением.
- exec_structured: environment windows или wsl, program, args (список), cwd, timeout_ms. Лучше запускать python.exe с полным путём к локальному скрипту. Не принимать строку «Process started» за доказательство завершения, проверить status и реальные выходные файлы.
- Ошибки Windows stdout CP1251 с Unicode: использовать Python -X utf8 либо безопасный ASCII-escaped диагностический вывод, не терять исходный UTF-8.
- При инструментальном отказе/запрете не обходить защиту, зафиксировать тип ошибки и проверить разрешённые альтернативы. Не объявлять PASS без результатов.

## Протокол исследования D09
1. Сверить последний CURRENT_CHECKPOINT и HANDOFF_NEW_CHAT с ROADMAP: следующий этап определяется ими, не исторической строкой R02.
2. Найти первичные работы с DOI, стандарты конкретной редакции, материалы производителей по конкретной модели, независимые исследования и сообщения Telegram. Практика → наука и наука → практика. Не принимать ни форумный совет, ни журнальную статью как непроверяемую истину.
3. Сохранять ссылку, авторов, год, точные страницы, таблицу, экспериментальные условия и качество источника: FULL_ORIGINAL_PDF/HTML; FULL_MACHINE_TEXT_ONLY; ABSTRACT_ONLY; INDEXED_SNIPPET; MANUFACTURER; FORUM. Не повышать уровень проверки без чтения оригинала.
4. Архивировать легально доступные исходные PDF внутри sources/Rxx/ и обязательно проверять сигнатуру %PDF, размер файла, SHA-256. Для PDF графиков и таблиц — визуальная проверка; не путать текстовую извлечённую таблицу со сканом, особенно после ошибок web screenshot cache miss.
5. Выделять U/I/T/SG(t), начальный SOC, конструкцию АКБ, ампер-часы/ватт-часы, метод C20/CCA/DCA/EIS, условия завершения, контролируемую группу, выборку и погрешность. Не считать микроциклы полными циклами; не смешивать исследования 2V и 12V, NAM/PAM, flooded и VRLA.
6. Для количественных результатов делать воспроизводимые отдельные Python-проверки в tools/, тестировать на синтетических/публичных данных. Успешный арифметический тест НЕ подтверждает эффективность реального заряда/восстановления.
7. Зафиксировать отрицательные результаты и противоречия; если нет независимого подтверждения, статус гипотеза, не факт. Не выдавать результаты лаборатории производителя за независимую репликацию.
8. Записать отдельный отчёт Rxx, обновить 01_SOURCES.md, CONCLUSIONS.md, HYPOTHESES.md, EXPERIMENT_PROTOCOL.md при необходимости, ROADMAP.md, CURRENT_CHECKPOINT.md, CHANGELOG.md. DECISIONS.md только при новом решении. Перезаписать HANDOFF_NEW_CHAT.md с последним статусом. Проверить файлы чтением.
9. Физические опыты не проводить без отдельного решения, метрологии, безопасного протокола; RD6018/БВ-600 не трогать. Предложения по изменению оборудования — только через D08, при наличии проверенного фактического расхождения, сперва полный dry-run на эмуляторе.

## Telegram @zaryadAKBin
Один разрешённый источник. Подробный канон доступа: TELEGRAM_CONNECTOR.md. Сервер локального stdio MCP: telegram_connector/telegram-research-plugin/server.py; виртуальное окружение telegram_connector/.venv/Scripts/python.exe; smoke test telegram_connector/test_mcp.py, проверка авторизованной сессии telegram_connector/verify_auth.py.
Четыре только читающих метода: recent_messages(limit,before_id), search_messages(query,limit), get_message(message_id), save_research_attachment(message_id). Отправки сообщений нет. MCP тестирован через SDK на HOME-PC, но не зарегистрирован отдельным ChatGPT плагином. Для доступа применять HOME-PC MCP; перед началом проверять реальную авторизацию.
Секреты: <LOCAL_SECRETS_FILE> (api_id/api_hash), локальная сессия: private/telegram_research.session. Не выводить значения секретов/файлы сессии в чат, не публиковать. Авторизованная сессия не требует повторного QR. При 2FA пароль вводится только локально на HOME-PC.
Локальная историческая выборка: sources/telegram/zaryadAKBin_recent_1800.jsonl, только 1800 сообщений из приблизительно 92940 по результату API на дату 28.11.2026; выводы не распространять на всё сообщество. Сопоставлять цепочки ответов по reply_to_msg_id, авторов, время, вложения и корректировки. Сообщения, копирующие наши собственные AI-ответы, не считать независимыми подтверждениями. Ранее широкий поиск блокировался инструментальной безопасностью, не обходить.
Профильный case: TELEGRAM_TRIAGE_001.md, основные исследования TG-01..TG-08. За медиа обращаться точечно; сырые данные и сессию оставлять локально и приватно.

## Проверенные локальные скрипты
- tools/r11_capacity_analysis.py — интегрирование Ah/Wh, cutoff и Пейкерт (synthetic PASS).
- tools/r12_identifiability.py — математика SOC/SOH (synthetic PASS).
- tools/r13_short_diagnostics_offline.py — модельный short/self-discharge (synthetic PASS).
- tools/r16_nbs_solubility_analysis.py, r16_validate_checkpoint.py — таблица NBS и хеши (PASS).
- tools/r17_quantitative_provenance.py, r17_validate_checkpoint.py — количественные результаты carbon/DCA, хеши и checkpoint (PASS).
- tools/r14_source_archive.py, r15_archive_sources.py, r16_archive_nist.py, r17_archive_public_sources.py — примеры архивирования публичных PDF с проверкой формата/хешей; файлы HTTP403/429/URLError считать недоступными, не архивированными.
При переходе в новый чат повторно проверять актуальный код и нужные тесты.

## Отказы и уроки
- Старый Telegram QR истекал: AUTH_TOKEN_EXPIRED. Исправлен код автоперевыпуска qr.recreate и HTML обновления; если уже авторизовано, не запускать QR заново.
- Неверно заявлялась недоступность HOME-PC, хотя он имелся через functions.exec: проверять ALL_TOOLS.
- PDF web screenshot cache miss: отдельно фиксировать MACHINE_TEXT_ONLY, для исходного PDF на HOME-PC использовать read_file с изображением нужной страницы.
- В первом локальном поиске Telegram Windows консоль ломалась на символах Unicode: предотвращать CP1251 ошибки.
- Локальный проект 28.11.2026 не имеет каталога .git. Файл .gitignore существует, но GitHub sync/backup НЕ организован и не подтвержден. Без решения владельца git init/push не выполнять.

## Новый чат — обязательное чтение
AGENTS.md → 00_CANON.md → HANDOFF_NEW_CHAT.md → RUNBOOK.md → OPERATOR_METHODS.md → ROADMAP.md → хвост CURRENT_CHECKPOINT.md → последний отчёт Rxx.
Не заниматься повторной археологией; продолжать R18, если HANDOFF и ROADMAP не изменены. Проверить сохранённые инструменты/файлы и сделать безопасный smoke test. Никаких незаявленных фоновых работ.

## Проверка передачи контекста перед выходом из чата
Запустить в Windows на HOME-PC: python.exe <RESEARCH_ROOT>\tools\validate_handoff.py. Этот тест сверяет AGENTS/RUNBOOK/HANDOFF/ROADMAP/checkpoint/регистры, файлы плагина и текущую локальную Git-ситуацию. Вывод HANDOFF_CONSISTENCY_PASS подтверждает только согласованность документов и наличие файлов; это НЕ Telegram-auth smoke test и не бэкап. После создания Git-репозитория пересмотреть утверждение о .git в самом тесте и handoff.

## GitHub NIR branch
Canonical RD6018 repository: `timspb/rd6018_bot`, default `main`. Dedicated NIR branch created 2026-11-28: `research/pb-acid-nir`, based on main SHA `70074de154b4c6f44614f2b4cfddf6ac77c55fbb`. Verified with branch search and compare (identical to main immediately after creation). URL https://github.com/timspb/rd6018_bot/tree/research/pb-acid-nir. Branch creation does not mean local Pb-Research is connected or content synchronized. Until explicit file sync, local <RESEARCH_ROOT> is canonical. Before uploading, inspect files for secrets/private Telegram content; exclude private/, .env.secrets, Telegram session, raw Telegram message dumps/media, local .venv and caches. Keep NIR artifacts in a dedicated subdirectory (e.g. research/pb-acid-nir/) and avoid production code/docs unless the user explicitly asks. Never merge to main or deploy from this branch by implication.