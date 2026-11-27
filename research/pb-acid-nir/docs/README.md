# Pb-Research
Научно-инженерная база по свинцово-кислотным АКБ. Цель — проверяемые выводы по электрохимии, диагностике, заряду, восстановлению и ресурсу.
Рабочий корень HOME-PC: <RESEARCH_ROOT>.

## Текущий статус
R19 PARTIAL: 22_R19_RECOVERY_DURABILITY.md — проверка краткого циклического и календарного follow-up восстановления. Два 40-cycle исследования найдены; длительного контролируемого multi-year inverse-charge trial для современных Ca/Ca/EFB/AGM не найдено. Следующий этап R20 — синтез выводов, evidence grades и no-go границ. Сверять HANDOFF_NEW_CHAT.md и ROADMAP.md.

## Структура
- AGENTS.md, 00_CANON.md, RUNBOOK.md — обязательный канон и порядок работы.
- 01_SOURCES.md — источники и уровни доступа.
- 03_R01.md и далее, включая 21_R18_POLARITY_REVERSAL.md и 22_R19_RECOVERY_DURABILITY.md — исследовательские отчёты.
- CONCLUSIONS.md, HYPOTHESES.md, EXPERIMENT_PROTOCOL.md — выводы, открытые гипотезы и безопасные планы проверки.
- TELEGRAM_CONNECTOR.md, TELEGRAM_TRIAGE_001.md — read-only форумная выборка и границы её охвата.
- HANDOFF_NEW_CHAT.md, OPERATOR_METHODS.md, CURRENT_CHECKPOINT.md — актуальная передача контекста.

## Ограничения
Никаких физических опытов с намеренной переполюсовкой, обратным зарядом, вскрытием VRLA или нештатными повышенными уставками без отдельного решения владельца и лабораторной оценки риска. Никаких изменений действующего RD6018, ESP/node104 или БВ-600 в рамках НИР. Производственная интеграция отдельно от исследования.

На 28.11.2026 локальный <RESEARCH_ROOT> не содержит .git и не синхронизируется автоматически. Публичные материалы экспортируются через tools/prepare_github_nir.py, проверяются tools/verify_public_export.py и публикуются только в research/pb-acid-nir ветки timspb/rd6018_bot. PDF originals, Telegram raw/cache/media, secrets/session и локальные case data в публичный экспорт не включаются.
