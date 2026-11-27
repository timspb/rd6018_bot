# История
2026-11-27/28: создан Pb-Research, канон, источники, отчеты R01–R03, R04-D, CASE-001. CASE-001 ограничен гарантийным обращением.
2026-11-28: оформлены README, RUNBOOK, ROADMAP, DECISIONS, HYPOTHESES, CONCLUSIONS, EXPERIMENT_PROTOCOL, INTEGRATION_RD6018. Начат R04; полные тексты и архив остаются открытой задачей.

2026-11-28: R04 литературный отчет, C10–C12, H11; уточнены границы заводских рекомендаций.

2026-11-28: R05, добавлены C13–C15, H12–H13 и протокол релаксации; попытка скачивания оригинала HTTP403.

2026-11-28: R06, C16–C18, H14, метрологический план DC измерений.

2026-11-28: R07, диагностическая матрица, C19–C21, H15.

2026-11-28: R08, C22–C24/H16; дополнение R04-D по уточнению Cyberpapa.

2026-11-28: D07 — уточнен приоритет беспристрастных исследований над реализацией RD6018/БВ-600.

2026-11-28: R09, D08, REC-001, C25–C27/H17–H18.

2026-11-28: R10, C28–C30/H19, критерии доказанного эффекта и остановки.

2026-11-28: Telegram @zaryadAKBin read-only MTProto authorized; local MCP tools/list, recent, search, invalid-input tests PASS. No Telegram sending functionality.

2026-11-28: first Telegram source triage TG-01..TG-08; plate-thickness image examined, negative Repair case logged; raw Telegram archive kept local and gitignored.

2026-11-28: D09 — закреплен двунаправленный протокол независимой проверки научных и практических источников.

2026-11-28: R11 C20/Пейкерт/температура; проверенный IEC 60095-1:2018 7.1.2, Pavlov JPS 2008 + отрицательный TG контроль. Синтетическая офлайн проверка математики PASS. ROADMAP R11 PARTIAL. Ни RD6018 ни БВ-600 не изменялись.

2026-11-28: R12 совместная наблюдаемость SOC/SOH и проверка независимости моделей; разобраны Wang 2021, Electronics 2023, JEST 2024/2026, VARTA и Telegram; аналитический offline test PASS. R12 PARTIAL. Код/железо RD6018 не тронуты.

2026-11-28: R13 soft-shorts / self-discharge, полнотекстовые Conradt 2023/2024, 5 выводов, 3 гипотезы, offline proof PASS; Roadmap R13 PARTIAL. REC-002 draft only; devices/code not modified.

2026-11-28: R14 конструктивная классификация Ca/Ca/EFB/AGM/GEL, 13 evidence refs, C45–C51/H30–H33, независимая матрица конструкция×назначение×газовый режим; JACI full PDF archived 2.3MB; R14 PARTIAL, R15 next; no device/firmware edits.

2026-11-28: R15 температура: Q(T) vs thermal ageing, калориметрия и поляризационное тепло, float Arrhenius heuristic bounded, межмодельные −3/−4mV(cell°C). Три исходных PDF архивированы, SHA256 записаны. C52–C58, H34–H37, R15 PARTIAL, R16 next, без RD/БВ деплоя.

2026-11-28: R16 electrolyte/grid-alloy science. Original NBS 1939 solubility and NBS 1934 conductivity PDFs archived+SHA256; NBS1939 Table5 visually validated; offline dataset/test 27 points PASS. Павлов 2008 C20-cycle tradeoff, Prengaman 2001 Ca/Sn/Ag metallurgical compromise, TG solubility-unit correction. C59–C66 H38–H42, ROADMAP R16 PARTIAL. No RD6018/БВ-600 changes.

2026-11-28: R17 carbon/NAM/PAM research. Two original open PDFs saved + SHA256; numerical carbon foam and NCC HRPSoC microcycles and Bozkaya short-term CA source-based check PASS; 2025–26 PAM carbon research added with strict abstract provenance. 9 conclusions C67–C75, 6 hypotheses H43–H48, roadmap R17 PARTIAL, R18 next, no RD/БВ modifications.

2026-11-28: по ревизии сохранения контекста добавлены OPERATOR_METHODS.md и HANDOFF_NEW_CHAT.md, RUNBOOK/AGENTS/README обновлены; исправлен stale R02 в AGENTS; локальная документация подтверждена, удалённая Git-синхронизация отсутствует/не подтверждена. Следующий R18, оборудование не трогали.

2026-11-28: Created dedicated GitHub branch `research/pb-acid-nir` in `timspb/rd6018_bot` from `main` SHA 70074de154b4c6f44614f2b4cfddf6ac77c55fbb. Verified branch exists and compare is identical (0 commits ahead/behind). No research content committed; local Pb-Research remains authoritative pending reviewed safe transfer. No main/production changes.

2026-11-28: NIR branch initial source import committed 4b0a9e5ab581c42e53ecac048ec9dbde5d20186b (50 safe new files, research/pb-acid-nir only); GitHub compare main verified ahead1/behind0; no sensitive data/PDFs/production modifications. Local handoff/runbook corrected: manual GitHub snapshot exists, auto-sync absent.

2026-11-28: R18 научная ревизия инверсии свинцовых элементов, предприняты и проверены 11 sources. Four primary/official original PDFs archived locally with SHA256; Nguyen thesis full web Ch3 only (local HTTPError), web screenshot cache miss. Independent positive counterexamples Perujo 2004 and Karami 2009 retained with limits; detected Karami baseline '<25%' conflict. OFFLINE math tools/r18_reversal_evidence_offline.py PASS. C76–C83 / H49–H53; roadmap R18 PARTIAL; R19 next. No physical, firmware or RD/BV actions.

2026-11-28: GitHub NIR R18 published 4236209b1438563feb96d23974b79594b0d94a2f; main ahead2/behind0, all 52 changed paths confined to research/pb-acid-nir. Validated R18 offline and public export, no secrets/production changes. Metadata handoff corrected to post-publication state.