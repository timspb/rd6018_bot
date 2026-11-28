# HANDOFF_NEW_CHAT — Pb-Research
Дата обновления: 2026-11-28.
NEXT_STAGE: R20
CURRENT_REPORT: 26_R20_CONTROLLED_COMPARISONS.md (parent synthesis 23_R20_SYNTHESIS.md; prior 25_R20_LONGITUDINAL_METROLOGY.md)
Не начинать повторно R01–R20; использовать отчёты, источники и ledgers.

## Среда и порядок
Рабочий корень HOME-PC: <RESEARCH_ROOT>. Инструменты через functions.exec → ALL_TOOLS → tools.mcp__mcp_gateway_home_pc__read_file/write_file/edit_block/exec_structured. Сверять tool schemas через ALL_TOOLS.
Чтение: AGENTS.md → 00_CANON.md → HANDOFF_NEW_CHAT.md → RUNBOOK.md → OPERATOR_METHODS.md → ROADMAP.md → CURRENT_CHECKPOINT.md → последний отчёт. Текущий этап брать из HANDOFF, ROADMAP и верхнего блока CURRENT_CHECKPOINT; нижняя часть checkpoint — исторический журнал.
D07/D09: независимая научная проверка, отличать full text/author copy/abstract/preview/forum anecdote, сохранять отрицательные результаты и противоречия. Не превращать отдельную статью в универсальный зарядный профиль.

## Текущий результат R20
R20 PARTIAL; 23_R20_SYNTHESIS.md. Синтезированы C01–C106 и H01–H67, присвоены уровни доказательности E1–E4 и переносимости T1–T4. Документ содержит тематические выводы R01–R19, разрешение кажущихся противоречий, no-go boundaries, требования к метрологии и требования к диагностической логике.
tools/r20_validate_synthesis.py PASS: 106 unique conclusion IDs, 67 unique hypothesis IDs, no gaps. r20_capacity_evidence_math.py, validate_handoff.py, r20_source_quality_audit.py also PASS. R20 — только документальная синтеза; не валидированный алгоритм, не программа зарядки и не разрешение на аппаратное внедрение.
R19 report 22_R19_RECOVERY_DURABILITY.md. Два 40-cycle studies (Karami 2009 inverse charge, Lee 2023 high-voltage extracted 2V cells), non-monotonic 10-week four-Gel series (Ohajianya 2021, no controls), Shi/Ferone/Rahn 2012/2013 residual aging, PNNL 18–28 month benchmark. R18 erratum adds Karami §3.4 40-cycle claim; exact ≥80% endurance metric/n/EOL unspecified.
R19 PDFs archived locally: sources/R19/SHA256SUMS.txt. Telegram scope only 1800 recent messages; no controlled longitudinal case. No full-history scrape.
No physical experiments, intentional cell reversal, reverse charge, VRLA opening, RD6018/ESP/node104/HA/BV-600 changes. All hardware implementation requires separate owner decision and dry-run.

## Next within R20
Prioritize the highest-impact open hypotheses and close source-quality gaps; do not turn the synthesis into a recipe. All H01–H67 remain open except H09 limited SUPPORTED in individual sources. R20 remains PARTIAL because full primary texts, independent replications and multi-month/multi-year matched data are incomplete.

## GitHub NIR
Repo timspb/rd6018_bot, branch research/pb-acid-nir, only research/pb-acid-nir/ paths. R20-A02 published content commit a9300486e03ef8c9801320dd6cf9d14ffdab1497 (verified branch main ahead8/behind0, 60 files all research/pb-acid-nir/); earlier A01 commit 3774ba3 preserved. Перед новым обновлением проверить актуальный tip; automatic sync отсутствует. Local <RESEARCH_ROOT> has no .git and no auto sync. Export tools/prepare_github_nir.py; audit tools/verify_public_export.py; handoff validator tools/validate_handoff.py; synthesis validator tools/r20_validate_synthesis.py.
Exclude PDFs, Telegram raw/cache/media, private/, .env.secrets, session/QR, local venv and private case data from public export. Never modify main, RD6018 runtime, ESP, node104 or BV-600 as part of this research task.

## R20-A01 — новый аудит качества источников (28.11.2026)
Новый отчёт 24_R20_EVIDENCE_GAP_AUDIT.md: Cleland2000 n126 new stored SLA, immediate +17% после опасного treatment, контроль и сроки отсутствуют, abstract 47/36.5% vs Results 46/36.5% (проверка Table2 OPEN); Mankov2026 новые AGM9Ah n2/300 циклов 7.8Ah/+4.5/+6.7% — профилактика, не восстановление; Catherino2004 критика мифа «80% излечимых» не равна статистике; Frenander2026 npj Clean Energy n54 — Li-ion, исключено. C92–C96, H60–H61. tools/r20_source_quality_audit.py PASS. Следующий предметный шаг: найти оригинальные таблицы/разметку групп и longitudinal matched C20/CCA/EFC data, а не переносить методы на оборудование.
R20-A01 успешно опубликован коммитом 3774ba35dd071156eb3f0a800262f81e80b7a229, включая отчет 24, скрипт и реестры; проверено compare с main. Не считать дальнейшие изменения автоматически синхронизированными. Локальный источник — <RESEARCH_ROOT>. Не синхронизировать private/Telegram/raw/PDF. RD6018/БВ-600/ESP/node104 без изменений.

## R20-A02 — метрология и продольная проверка (28.11.2026)
Отчёт 25_R20_LONGITUDINAL_METROLOGY.md. ZVEI Leaflet34/2020 FULL WEB ORIGINAL, scope stationary, локальное скачивание TLS timeout. Shamim/PNNL Energies 15(9)3389/2022 FULL ORIGINAL PDF в sources/R20 (не публиковать PDF на GitHub), 4 AGM по одному на 4 режима, 18–28 месяцев. Reference capacity — среднее двух C5 до 11.1V, не C20! Initial capacity rebound PS при обычной эксплуатации без recovery treatment; после 400 PS cycles изменена charge termination и RTE смешивается с эффектом протокола. B03 Mizumoto2018 rechecked source index; no new full PDF. C97–C101/H62–H64, tools/r20_capacity_evidence_math.py purely synthetic sigma illustration, not instrument calibration. NEXT within R20: verified matched treatment-vs-ordinary-charge studies with longitudinal reference C20/CCA/EFC and independent n; inspect full Cleland Table2 and Mankov methodology, without hazardous physical protocols. No charger/hardware changes. Published research content at a9300486 has been independently verified in GitHub; local handoff metadata can require a later minor GitHub commit. Use HEAD on research/pb-acid-nir, not stale commit IDs, for continuation.

## R20-A03 — актуальный следующий шаг
Cooper 2002 (6 AGM pairs, no C20, original PDF 403); Lam 1995 (PCL, 2V cells, negative and positive pulse results); Fraunhofer 2002 (OPzV case and separate field maintenance cohort). R20 remains PARTIAL. Next: obtain Wagner/Sauer 2001 and Sandia 1998 primary papers, distinguish cohort overlap and extract long-term data; Cleland Table2 and Mankov full text remain OPEN. Local changes pending verification of publication; no firmware/hardware changes.
R20-A03 local checks PASS; Local archival verification: Lam_CSIRO_1995_PCL.pdf, 1,448,455 bytes, SHA256 de1cfe1717603708c660390d0db8d093b2787fedb82d60a51419fe617625243e; Fraunhofer_ISE_Annual_Report_2002.pdf, 2,400,106 bytes, SHA256 e1fd864eb4d623524753270c3818701cd849bf90378bf0b44fc494388cb48428. Both in sources/R20, excluded from GitHub. Cooper official PDF remains HTTP403.
