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

2026-11-28: R19 PARTIAL — 22_R19_RECOVERY_DURABILITY.md. Found/verified two 40-cycle follow-ups (Karami 2009 inverse charge; Lee et al 2023 high-voltage restored 2V cells), one non-monotonic 10-week pulse-desulfation series (Ohajianya 2021), Shi/Ferone/Rahn one-cell 313h desulfation with residual aging, PNNL 18–28 month/289–728 EFC durability benchmark, and corrected IEC 60095-1 preview 2026-02. Local Telegram 1800 sample no controlled longitudinal case. tools/r19_durability_analysis.py PASS; sources/R19/SHA256SUMS.txt generated. Corrected R18 S06 to include 40-cycle claim and undefined endurance metric. No physical/production changes. NEXT R20 synthesis.

2026-11-28: R19 published to GitHub NIR branch as b410ff161e7e1f2cfa8a756616a37ef0dd7a7c11. Added durability report, R18 Karami 40-cycle erratum, sources/conclusions/hypotheses/protocol, Telegram triage, offline analysis and R20 handoff. Pre-publication compare main ahead3/behind0; only research/pb-acid-nir paths touched. Local source PDFs remain excluded from public export. R19 PARTIAL; R20 next.

2026-11-28: R20 PARTIAL — 23_R20_SYNTHESIS.md consolidates C01–C91 and H01–H59, evidence levels E1–E4, transferability T1–T4, no-go boundaries, metrology and diagnostic requirements. R20 validator confirms 91 unique conclusions and 59 unique hypotheses. Roadmap R20 PARTIAL; no charger algorithm, firmware or hardware changes. Next work stays inside R20: prioritize and close source/data gaps; physical validation requires separate owner decision.

2026-11-28: R20-A01 new source-quality audit A01–A04, identified Cleland count 46/47 inconsistency, small-n Mankov 300-cycle prevention vs restoration, Catherino 80% sulfation myth as unmeasured claim, excluded new Nature Li-ion pulse article; C92–C96 H60–H61. R20 scientific priority matrix, offline arithmetic PASS, no hardware. Pending NIR branch sync.

2026-11-28: R20-A01 published commit 3774ba35dd071156eb3f0a800262f81e80b7a229; GitHub ahead6/behind0, all paths research/pb-acid-nir. Local handoff/checkpoint metadata refreshed to published state (followup metadata sync separate).

- 2026-11-28 R20-A02: Added 25_R20_LONGITUDINAL_METROLOGY.md (ZVEI 2020, PNNL Shamim 2022, Mizumoto reassessment); first original PDF archived in sources/R20 and SHA256 registered; C97–C101/H62–H64; tools/r20_capacity_evidence_math.py analytical sensitivity; no physical experiments or production modifications. Local source of truth; GitHub sync requires explicit audit/public export.

2026-11-28 R20-A03: controlled comparative evidence Cooper/Lam/Fraunhofer; new 26_R20_CONTROLLED_COMPARISONS.md; C102–C106/H65–H67 and numerical Cooper audit; no hardware changes.

2026-11-28 R20-A04: 27_R20_REVERSIBLE_LOSS_LIMITS.md, C107–C112/H68–H70, r20_reversible_loss_audit.py, 10.5-year selected-cell evidence and 81-specimen storage study.

2026-11-28 R20-A05: 28_R20_PCL_IDENTIFIABILITY.md; C113–C117/H71–H72; r20_pcl_identifiability.py; distinguish EIS correlation and chemical classification; A04 publication verified.

2026-11-28 R20-A06–A08: reports 29–31, raw EIS, zHit and residual capacity, multifeature baselines; C118–C129/H73–H76 appended. No hardware changes.

2026-11-28 R20-A09: 32_R20_REST_HISTORY.md, r20_rest_history_audit.py, C130–C132/H77. Prelabel rest/history features, common-case joint models. A06–A08 published c253fc44e933d7baa9fe0defb518860c2ca28b52.

2026-11-28 R20-A10: report 33, coverage audit, independent dataset admission, C133–C135/H78. A09 published 84e8d84e573ad3eb0be63dc09baf7e09d6ba2711.

2026-11-28 S1/A11: RESEARCH_ACCEPTANCE.md (88 gates, 39 baseline, 40 current), long sprint plan; report 34, OPzS alignment, DCA/stratification evidence; C136–C139/H79. A10 published d1253f88d3fb0020a0daee502484b3f3e9da62bb.

2026-11-29 S1 block2: reports35–36, C140–146/H80–81, 43/88; four PDFs locally archived, two arithmetic tools executed; no production changes.

2026-11-29 S1 block3: report37, C147–C149/H82, 44/88; two primary PDFs archived and arithmetic checked. Previous S1 block2 published eb3b8791. No production edits.

2026-11-29 S1 block4: report38, C150–153/H83, 48/88; two verified originals, synthetic audit, four bounded K accepted. S1 deliverable complete, S2 next; block3 published 4ed23d12. No production changes.

2026-11-29 S2 block1 report39, C154–157/H84, 49/88, R03-K documentary accepted. Minami PDF archived, James arithmetic checked. S1 published 9fadd9f6. No hardware.

2026-11-29 S2 block2 report40, C158–161/H85, 50/88, R19-K bounded documentary accepted. Sandia original archived; INL archive blocked. Block1 published 58f5226a. No hardware.

2026-11-29 S2 block3 report41, C162–164/H86, 52/88, R17/R18-K documentary accepted; Hu original archived. Block2 published 27d0735f. No equipment.

2026-11-29 S2 exit/S3 admission report42, C165–166/H87, 52/88 unchanged; signed metrology synthetic PASS; OPzS rest screen negative; BBOXX download denied. Block3 published c2d1e3b6.

2026-11-29 S3 block1 report43, C167–171/H88, 54/88; R04-D/R13-K accepted bounded, Conradt erratum; three original manufacturer PDFs archived. Prior published 89e2e15e. No hardware.

2026-11-29 S3 block2 report44, C172–175/H89, 55/88, R11-K documentary accepted; five Zenodo files verified and metrics reproduced. Prior published 35c6553f. No equipment.
