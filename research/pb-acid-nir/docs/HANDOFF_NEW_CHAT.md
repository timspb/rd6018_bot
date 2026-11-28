# HANDOFF_NEW_CHAT — Pb-Research
Дата обновления: 2026-11-28.
NEXT_STAGE: R20
CURRENT_REPORT: 23_R20_SYNTHESIS.md
Не начинать повторно R01–R20; использовать отчёты, источники и ledgers.

## Среда и порядок
Рабочий корень HOME-PC: <RESEARCH_ROOT>. Инструменты через functions.exec → ALL_TOOLS → tools.mcp__mcp_gateway_home_pc__read_file/write_file/edit_block/exec_structured. Сверять tool schemas через ALL_TOOLS.
Чтение: AGENTS.md → 00_CANON.md → HANDOFF_NEW_CHAT.md → RUNBOOK.md → OPERATOR_METHODS.md → ROADMAP.md → CURRENT_CHECKPOINT.md → последний отчёт. Текущий этап брать из HANDOFF, ROADMAP и верхнего блока CURRENT_CHECKPOINT; нижняя часть checkpoint — исторический журнал.
D07/D09: независимая научная проверка, отличать full text/author copy/abstract/preview/forum anecdote, сохранять отрицательные результаты и противоречия. Не превращать отдельную статью в универсальный зарядный профиль.

## Текущий результат R20
R20 PARTIAL; 23_R20_SYNTHESIS.md. Синтезированы C01–C96 и H01–H61, присвоены уровни доказательности E1–E4 и переносимости T1–T4. Документ содержит тематические выводы R01–R19, разрешение кажущихся противоречий, no-go boundaries, требования к метрологии и требования к диагностической логике.
tools/r20_validate_synthesis.py PASS: 96 unique conclusion IDs, 61 unique hypothesis IDs, no gaps. R20 — только документальная синтеза; не валидированный алгоритм, не программа зарядки и не разрешение на аппаратное внедрение.
R19 report 22_R19_RECOVERY_DURABILITY.md. Два 40-cycle studies (Karami 2009 inverse charge, Lee 2023 high-voltage extracted 2V cells), non-monotonic 10-week four-Gel series (Ohajianya 2021, no controls), Shi/Ferone/Rahn 2012/2013 residual aging, PNNL 18–28 month benchmark. R18 erratum adds Karami §3.4 40-cycle claim; exact ≥80% endurance metric/n/EOL unspecified.
R19 PDFs archived locally: sources/R19/SHA256SUMS.txt. Telegram scope only 1800 recent messages; no controlled longitudinal case. No full-history scrape.
No physical experiments, intentional cell reversal, reverse charge, VRLA opening, RD6018/ESP/node104/HA/BV-600 changes. All hardware implementation requires separate owner decision and dry-run.

## Next within R20
Prioritize the highest-impact open hypotheses and close source-quality gaps; do not turn the synthesis into a recipe. All H01–H61 remain open except H09 limited SUPPORTED in individual sources. R20 remains PARTIAL because full primary texts, independent replications and multi-month/multi-year matched data are incomplete.

## GitHub NIR
Repo timspb/rd6018_bot, branch research/pb-acid-nir, only research/pb-acid-nir/ paths. Latest published branch tip before R20: b83a1b3313fbcbe2a16bee69ece9bb599a587615 (verify current tip and compare main before next update). Local <RESEARCH_ROOT> has no .git and no auto sync. Export tools/prepare_github_nir.py; audit tools/verify_public_export.py; handoff validator tools/validate_handoff.py; synthesis validator tools/r20_validate_synthesis.py.
Exclude PDFs, Telegram raw/cache/media, private/, .env.secrets, session/QR, local venv and private case data from public export. Never modify main, RD6018 runtime, ESP, node104 or BV-600 as part of this research task.

## R20-A01 — новый аудит качества источников (28.11.2026)
Новый отчёт 24_R20_EVIDENCE_GAP_AUDIT.md: Cleland2000 n126 new stored SLA, immediate +17% после опасного treatment, контроль и сроки отсутствуют, abstract 47/36.5% vs Results 46/36.5% (проверка Table2 OPEN); Mankov2026 новые AGM9Ah n2/300 циклов 7.8Ah/+4.5/+6.7% — профилактика, не восстановление; Catherino2004 критика мифа «80% излечимых» не равна статистике; Frenander2026 npj Clean Energy n54 — Li-ion, исключено. C92–C96, H60–H61. tools/r20_source_quality_audit.py PASS. Следующий предметный шаг: найти оригинальные таблицы/разметку групп и longitudinal matched C20/CCA/EFC data, а не переносить методы на оборудование.
GitHub sync этого блока и R20 ранее не был подтверждён; всегда проверять ветку research/pb-acid-nir перед записью. Локальный источник — <RESEARCH_ROOT>. Не синхронизировать private/Telegram/raw/PDF. RD6018/БВ-600/ESP/node104 без изменений.