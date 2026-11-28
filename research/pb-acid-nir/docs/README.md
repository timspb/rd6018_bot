# Pb-Research
Научно-инженерная база по свинцово-кислотным АКБ. Цель — проверяемые выводы по электрохимии, диагностике, заряду, восстановлению и ресурсу.
Рабочий корень HOME-PC: <RESEARCH_ROOT>.

## Текущий статус
R20 PARTIAL: 23_R20_SYNTHESIS.md — синтез C01–C96 и H01–H61, evidence grades E1–E4, переносимость T1–T4, диагностические требования и no-go границы. Это документальная синтеза, не валидированный алгоритм и не разрешение на физический опыт. Сверять HANDOFF_NEW_CHAT.md и ROADMAP.md.

## Структура
- AGENTS.md, 00_CANON.md, RUNBOOK.md — обязательный канон и порядок работы.
- 01_SOURCES.md — источники и уровни доступа.
- 03_R01.md и далее, включая 21_R18_POLARITY_REVERSAL.md, 22_R19_RECOVERY_DURABILITY.md и 23_R20_SYNTHESIS.md — исследовательские отчёты.
- CONCLUSIONS.md, HYPOTHESES.md, EXPERIMENT_PROTOCOL.md — выводы, открытые гипотезы и безопасные планы проверки.
- TELEGRAM_CONNECTOR.md, TELEGRAM_TRIAGE_001.md — read-only форумная выборка и границы её охвата.
- HANDOFF_NEW_CHAT.md, OPERATOR_METHODS.md, CURRENT_CHECKPOINT.md — актуальная передача контекста.

## Ограничения
Никаких физических опытов с намеренной переполюсовкой, обратным зарядом, вскрытием VRLA или нештатными повышенными уставками без отдельного решения владельца и лабораторной оценки риска. Никаких изменений действующего RD6018, ESP/node104 или БВ-600 в рамках НИР. Производственная интеграция отдельно от исследования.

На 28.11.2026 локальный <RESEARCH_ROOT> не содержит .git и не синхронизируется автоматически. Публичные материалы экспортируются через tools/prepare_github_nir.py, проверяются tools/verify_public_export.py и публикуются только в research/pb-acid-nir ветки timspb/rd6018_bot. PDF originals, Telegram raw/cache/media, secrets/session и локальные case data в публичный экспорт не включаются.

Дополнение R20-A01: 24_R20_EVIDENCE_GAP_AUDIT.md — аудит источников, устранение путаницы между восстановлением и профилактикой, исключение Li-ion статей из Pb-acid и приоритеты научной валидации; tools/r20_source_quality_audit.py offline PASS.