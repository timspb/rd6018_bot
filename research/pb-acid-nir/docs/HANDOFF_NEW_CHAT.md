# HANDOFF_NEW_CHAT — актуальный снимок для продолжения Pb-Research
Состояние проверено: 28.11.2026. Не начинать исследования R01–R17 заново.

## Где и как работать
Корень HOME-PC: <RESEARCH_ROOT>, WSL: /mnt/e/CODEX/Pb-Research. Запуск через functions.exec → ALL_TOOLS → tools.mcp__mcp_gateway_home_pc__read_file/write_file/edit_block/exec_structured. Подробности OPERATOR_METHODS.md. Проверить фактическую доступность, не выводить секреты.
Обязательно прочесть AGENTS.md, 00_CANON.md, RUNBOOK.md, OPERATOR_METHODS.md, ROADMAP.md и последние строки CURRENT_CHECKPOINT.md. Границы D07/D09: независимая наука, двусторонняя проверка Telegram и публикаций, никакого доверия авторитету вместо измерений.

## Текущая работа
R17 «Углерод и активные массы» = PARTIAL. Главный отчёт 20_R17_CARBON_ACTIVE_MASS.md; 14 источников, C67–C75, H43–H48. Оригиналы Bozkaya 2022 (8 стр.) и обзор Lach 2019 (13 стр.) реально сохранены в sources/R17 и проверены SHA-256; результаты Xie 2024 и NCC 2023 по микроциклам пока без локально архивированного полного PDF. Проверки tools/r17_quantitative_provenance.py и tools/r17_validate_checkpoint.py PASS в прошлом сеансе; при необходимости повторить. PAM AGM 2025–2026 доступен лишь по аннотациям/индексированному тексту — не завышать статус.
Следующий плановый этап **R18: переполюсовка и её последствия**, ROADMAP OPEN. После него R19 (ресурс/устойчивость восстановления), R20 (синтез алгоритмов). Сейчас: 1 DONE, 18 PARTIAL, 3 OPEN (всего 22 с R04-D); эти статусы относятся к литературному исследованию, не к физической верификации.
R18 должен разделить переполюсовку одного слабого элемента при разряде последовательной батареи, ошибочно обратное подключение клемм и намеренное физическое изменение полярности пластин. Любые реальные эксперименты запрещены без отдельного задания и оценки опасности.

## Источники и инструменты
Telegram @zaryadAKBin: авторизованная локальная сессия, 4 read-only stdio MCP-инструмента на HOME-PC, регистрация в ChatGPT как отдельного плагина НЕ выполнена. TELEGRAM_CONNECTOR.md. API-учётные данные только <LOCAL_SECRETS_FILE>, файл сессии только private. Не читать/публиковать session bytes.
Локальная выборка 1800 из примерно 92940 сообщений; не вся история. TELEGRAM_TRIAGE_001.md. В поиске последних 1800 R17 не найдено прямых контролируемых опытов по carbon-additives, это не означает отсутствие во всём Telegram.
Отчёты R11–R17 лежат в корне 14_R11_... — 20_R17_...; список доказательств 01_SOURCES.md, CONCLUSIONS.md, HYPOTHESES.md, результаты CASE-001 в cases/. Отдельно регистрировать исходные методы, неопределённости, отрицательные результаты.

## Границы и синхронизация
RD6018, ESP, node104 и БВ-600 не изменялись в текущем цикле исследований. INTEGRATION_RD6018.md содержит только научные кандидатные идеи, не переданные задания в разработку. Ниже порога независимой проверки научные гипотезы не являются уставками или критерием запуска.
28.11.2026 проверено: в корне НЕТ .git; данные сохраняются локально, автоматический remote backup/GitHub sync не подтвержден. .gitignore содержит private/ и источники Telegram, но без .git не обеспечивает архивирование и сам не защищает сессию от ручной передачи. Не создавать репозиторий и не отправлять данные без отдельного решения владельца.

## Как закончить следующий этап
Отчёт R18, проверки/архивы по возможности → 01_SOURCES/CONCLUSIONS/HYPOTHESES → ROADMAP → CURRENT_CHECKPOINT/CHANGELOG → обновить этот HANDOFF_NEW_CHAT.md (rewrite) → перечитать файлы и убедиться в непротиворечивости. При отсутствии полного первоисточника оставить PARTIAL, не выдумывать данные и не тормозить другие темы.

Проверка операторского handoff: python.exe <RESEARCH_ROOT>\tools\validate_handoff.py → HANDOFF_CONSISTENCY_PASS (28.11.2026). Без доступа к секретам, без обращения к Telegram и без GitHub.

## GitHub research branch (created 28.11.2026)
Repository: https://github.com/timspb/rd6018_bot. Dedicated branch: `research/pb-acid-nir` — https://github.com/timspb/rd6018_bot/tree/research/pb-acid-nir. Created successfully from `main`, base SHA `70074de154b4c6f44614f2b4cfddf6ac77c55fbb`; compare main...research/pb-acid-nir = identical (ahead 0/behind 0). Branch exists and is verified. No Pb-Research files have yet been committed to it; local research remains authoritative in <RESEARCH_ROOT>. No main, other branches, runtime code or physical devices changed. Next sync should transfer only reviewed non-secret research docs/sources into a clearly isolated directory on this branch, never Telegram session, .env, raw private message cache or unrelated RD code. Local project still has no .git, so no local branch/worktree is checked out.