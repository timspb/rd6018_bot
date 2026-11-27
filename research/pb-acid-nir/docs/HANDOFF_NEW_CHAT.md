# HANDOFF_NEW_CHAT — Pb-Research
Дата обновления: 2026-11-28.
NEXT_STAGE: R19
CURRENT_REPORT: 21_R18_POLARITY_REVERSAL.md
Не начинать повторно R01–R18.

## Среда и методика
Рабочий корень HOME-PC: <RESEARCH_ROOT>. В ChatGPT инструменты HOME-PC доступны через functions.exec → ALL_TOOLS → tools.mcp__mcp_gateway_home_pc__read_file/write_file/edit_block/exec_structured. Последовательность чтения: AGENTS.md, 00_CANON.md, HANDOFF_NEW_CHAT.md, RUNBOOK.md, OPERATOR_METHODS.md, ROADMAP.md, последние строки CURRENT_CHECKPOINT.md, последний отчет. Не печатать приватные сессии и секреты.
D07/D09: научное исследование независимо от RD6018/БВ-600; проверять публикации и профильный Telegram двунаправленно, не принимать советы и заявления без условий и контрольных измерений. PARTIAL относится к литературной базе, не к лабораторной приемке.

## Итог R18
R18 «Переполюсовка и последствия» PARTIAL. Отчет 21_R18_POLARITY_REVERSAL.md, 11 источников, C76–C83, H49–H53. Четыре оригинала в sources/R18 (Mooney 2017, Karami 2009, ZVEI 2011 и US Army TM11-430), SHA256 в отчете. PhD Nguyen 2009 Chapter 3 прочитана по полному web-тексту, но PDF не загружен на HOME-PC (HTTPError), визуальные рисунки не проверены. Perujo 2004 n=2 carbon-fibre пережили случайную инверсию, но долгосрочное испытание в публикации ограничено одним PV accelerated cycle. Karami 2009 пять flooded 40Ah: среднее 7.2→35.0Ah после многостадийной обработки; влияние обратного заряда не выделено из смены электролита и обычной зарядки; текстовая формулировка «все исходные <25%» противоречит 13/40=32.5%, 10/40=25% в Table1. Опасные испытания не повторять.
tools/r18_reversal_evidence_offline.py — локальный синтетический PASS; 6-cell Utotal может маскировать одну Ucell<0. Все источники, ограничения, сценарии в отчете.
В локальном Telegram архиве 1800 последних сообщений по @zaryadAKBin найден лишь недоказательный пост 105999; полноценную историю 92940 сообщений не проверяли. Доступ через telegram_connector/telegram-research-plugin/server.py, только read-only, отдельный ChatGPT plugin не установлен. Секреты только <LOCAL_SECRETS_FILE>, сессия только private; не распространять.
Стадии: R00 DONE, R01–R18 (включая R04-D) PARTIAL; R19/R20 OPEN.

## GitHub НИР
timspb/rd6018_bot, ветка research/pb-acid-nir, только каталог research/pb-acid-nir/. Первичная публикация 4b0a9e5ab581c42e53ecac048ec9dbde5d20186b. R18 отчет подготовлен для проверенного следующего коммита. Последний SHA проверить на GitHub, не считать локальные данные автоматически синхронизированными. В корне <RESEARCH_ROOT> нет .git. Экспорт: tools/prepare_github_nir.py; аудит: tools/verify_public_export.py; загрузка только после проверки. Не передавать Telegram raw/cache/session/QR, env secrets, private, сторонние PDF и локальные venv. Никаких изменений main, кода/прошивок RD6018, node104 или БВ-600 без отдельной задачи.

## Следующая задача R19
Долгосрочная устойчивость восстановленной емкости: независимый C20/CCA после недель, месяцев и заданных циклов, контрольный обычный заряд, matched контрольные образцы, повторяемость, саморазряд, газ и потери воды, негативные случаи и маркировка dropout. Потом R20 научный синтез. По окончании: отчет и источники → conclusions/hypotheses/roadmap → CURRENT_CHECKPOINT/CHANGELOG → перезаписать этот handoff → tools/validate_handoff.py → проверенный public export → GitHub NIR-only commit → compare main.