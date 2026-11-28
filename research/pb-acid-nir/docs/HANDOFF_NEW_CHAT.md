# HANDOFF_NEW_CHAT — Pb-Research
Дата обновления: 2026-11-29.
NEXT_STAGE: R20
CURRENT_REPORT: 54_S5_CYBERPAPA_CUTOFF_UPS.md (parent 23_R20_SYNTHESIS.md; RESEARCH_ACCEPTANCE.md)
Не начинать повторно R01–R20; использовать отчёты, источники и ledgers.

## Среда и порядок
Рабочий корень HOME-PC: <RESEARCH_ROOT>. Инструменты через functions.exec → ALL_TOOLS → tools.mcp__mcp_gateway_home_pc__read_file/write_file/edit_block/exec_structured. Сверять tool schemas через ALL_TOOLS.
Чтение: AGENTS.md → 00_CANON.md → HANDOFF_NEW_CHAT.md → RUNBOOK.md → OPERATOR_METHODS.md → ROADMAP.md → CURRENT_CHECKPOINT.md → последний отчёт. Текущий этап брать из HANDOFF, ROADMAP и верхнего блока CURRENT_CHECKPOINT; нижняя часть checkpoint — исторический журнал.
D07/D09: независимая научная проверка, отличать full text/author copy/abstract/preview/forum anecdote, сохранять отрицательные результаты и противоречия. Не превращать отдельную статью в универсальный зарядный профиль.

## Текущий результат R20
R20 PARTIAL; 23_R20_SYNTHESIS.md. Синтезированы C01–C139 и H01–H79, присвоены уровни доказательности E1–E4 и переносимости T1–T4. Документ содержит тематические выводы R01–R19, разрешение кажущихся противоречий, no-go boundaries, требования к метрологии и требования к диагностической логике.
tools/r20_validate_synthesis.py PASS: 139 unique conclusion IDs, 79 unique hypothesis IDs, no gaps. r20_capacity_evidence_math.py, validate_handoff.py, r20_source_quality_audit.py also PASS. R20 — только документальная синтеза; не валидированный алгоритм, не программа зарядки и не разрешение на аппаратное внедрение.
R19 report 22_R19_RECOVERY_DURABILITY.md. Два 40-cycle studies (Karami 2009 inverse charge, Lee 2023 high-voltage extracted 2V cells), non-monotonic 10-week four-Gel series (Ohajianya 2021, no controls), Shi/Ferone/Rahn 2012/2013 residual aging, PNNL 18–28 month benchmark. R18 erratum adds Karami §3.4 40-cycle claim; exact ≥80% endurance metric/n/EOL unspecified.
R19 PDFs archived locally: sources/R19/SHA256SUMS.txt. Telegram scope only 1800 recent messages; no controlled longitudinal case. No full-history scrape.
No physical experiments, intentional cell reversal, reverse charge, VRLA opening, RD6018/ESP/node104/HA/BV-600 changes. All hardware implementation requires separate owner decision and dry-run.

## Next within R20
Prioritize the highest-impact open hypotheses and close source-quality gaps; do not turn the synthesis into a recipe. All H01–H79 remain open except H09 limited SUPPORTED in individual sources. R20 remains PARTIAL because full primary texts, independent replications and multi-month/multi-year matched data are incomplete.

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

## R20-A04 — current next step
Bopp 2010 10.5-year Talhof endpoint, selected failed/functional cells and monitoring gap; same cohort as Wagner/Sauer 2001. 81 small GEL storage factorial, not C20. Hund 1998 SG vs final capacity and Energies 2019 no final standardized discharge. Next: PCL mechanisms (grid/PAM interface vs sulfate), independent automotive-relevant sources and archival evaluation of diminishing-return criterion. Cleland Table2/Mankov full text remain OPEN. Prior A03 GitHub commit 2dc7f9740f51540282c57260c7e5ba915fd4475f; A04 local changes require publication check. No hardware changes.

## R20-A05 — current next step
PCL interface abstracts; Kwiecien/Badeda original PDF text rechecked, not independent new trials, web screenshots failed. 2026 field cohort indexed text only; full paper and direct physical labels not established. Exact synthetic grid/interface nonidentifiability. Next retrieve raw EIS supplement and independent labeled aging data, and evaluate held-out diagnostic baseline. A04 published 111c2d42491e88a1a45a932adef5590d134de840. A05 local changes require publication check. No hardware changes.


## R20-A06 — локальный результат, публикация ожидает согласованного экспорта
29_R20_RAW_EIS_AND_LABELS.md сохранён; tools/r20_eis_raw_audit.py выполнен: 2104/2104 MAT, 4 физические ячейки, 35 checkups, 65 selected spectra. ZIP источника в sources/R20/Kwiecien_2018_supplement_alt.zip, SHA256 96d49538c06b931c77cde65bbfedf7aa5584c049dcd30e336938c1c18197f60a. R20-A06 preliminary raw ratios only; zHit, independent scipy decode and capacity integration pending. Candidate C118–C123/H73–H74 in report, not counted in ledger. Batch registry update rejected; retain A05 validated registry (117/72) and GitHub 86f44ebc until consistent export. Next read report 29 first. No hardware changes.


## R20-A07 — latest local research result
Read 30_R20_ZHIT_AND_CAPACITY.md after report 29. zHit Python transcription: 2104 spectra; 56721/78962 interior points within native threshold; -3/-1 bias comparison, mini-cycle repeatability. 38 trace files, 661329 rows; 39 residual capacity candidates, 31 nonbaseline, 26 joined valid rows, four leave-one-cell-out folds; FCE baseline wins 3/4 against 1kHz, 4/4 against 10Hz. Scripts r20_eis_zhit_audit.py, r20_eis_capacity_candidates.py, r20_eis_capacity_join.py executed. Not fully charged C20, no chemical or hardware validation. Candidate C124–C127/H75 saved in report; A06/A07 consistent ledger and export pending, published HEAD remains last verified A05 unless separately checked. Next independent MAT decoder, units and author mask, timestamp alignment and larger independent dataset. No hardware changes.

## R20-A08 current handoff
Reports 29–31, local ledger C129/H76, original dataset 2104 spectra and 38 traces from 4 cells. Fixed leave-one-cell-out primary 26 observations: FCE ridge better than tested multiband variants; 24-row sensitivity metric-dependent. No confirmed incremental advantage. Next verify independent pre-discharge voltage/rest/time alignment and external cohort. No hardware changes. Publication status verify against actual branch HEAD.

## R20-A09 current handoff
Report 32; script r20_rest_history_audit.py; 31 four-hour rest cases, 26 EIS complete cases. Equal Urest with 11-fold residual Q difference; combined model only exploratory improvement on selected set. Freeze before further validation; next coverage-aware fallback on 31 and independent larger raw dataset. A06–A08 GitHub c253fc44e933d7baa9fe0defb518860c2ca28b52. No equipment changes.

## R20-A10 current handoff
Read report 33. Full coverage audit complete on original four cells; no further tuning. OPzS original six ZIPs + PDF and BBOXX metadata/readme in sources/R20, hashes in SHA256SUMS.txt. No released OPzS density; duplicate timestamps and temperature label mismatch. Next source/test-specific alignment, independent discharge integration; BBOXX telemetry in staged subsets, current sign and censoring checks. A09 commit 84e8d84e573ad3eb0be63dc09baf7e09d6ba2711. No equipment changes.

## S1 long sprint current handoff
Read RESEARCH_ACCEPTANCE.md then report 34. Baseline 39/88, current 40/88; 139 conclusions, 79 hypotheses. OPzS strict alignment executed, 5 nominal-rate blocks, no verified capacity labels. R01-Q accepted from measured SG and DCA primary quantitative text. Continue S1 gas/water/corrosion, R02 microscopy, MAIN/MIX/desulfation and practical D09 evidence. Do not return to repetitive four-cell fitting. A10 GitHub d1253f88d3fb0020a0daee502484b3f3e9da62bb. No physical testing or production changes.

## S1 block2 current handoff
Read RESEARCH_ACCEPTANCE.md, 35_S1_GAS_SULFATE_MAIN.md and 36_S1_TRANSFER_AND_MIX.md. 43/88 documentary gates; C146/H81. R02/R04/R14 quantitative primary gates accepted. Next S1 full controlled MIX/stratification and model-specific criteria/protocol matrix, do not claim universal U/I. Existing forum cases compared, no new Telegram raw access. Four primary PDFs archived; screenshot unavailable, source-specific limits recorded. No hardware tests. Verify GitHub HEAD separately.

## S1 block3 current handoff
Read report37 and RESEARCH_ACCEPTANCE.md. C149/H82, 44/88. R09-K documentary separation PASS; R09-Q/P still OPEN. New primary PDFs in sources/S1. No independently verified optimal MIX or upper/lower universal threshold. Next finish model-specific matrix, independent metrology/control protocols, remaining S1 critical reviews before S2. No production/hardware. Previous verified HEAD eb3b87917d2ea8733876cee9e04a4bab5e3d2d85; confirm current HEAD.

## S1 exit / S2 current handoff
Read report38 and RESEARCH_ACCEPTANCE.md. C153/H83, 48/88. S1 deliverable complete, model-specific validation and named open gates carry forward. Next S2 matched recovery/control, waveform, resource and negative cases (R03,R17,R18,R19). Cleland/Mankov gaps, seek independent contemporary primary studies. No repeating same inaccessible source indefinitely; no equipment/production changes. Prior verified GitHub HEAD 4ed23d12b5c40b231cfd7e293e6aaafd87c6fc21; verify current.

## S2 block1 current handoff
Read RESEARCH_ACCEPTANCE.md and report39. C157/H84, 49/88. R03-K documentary PASS; R03-P/R19-K/P OPEN. James totals vs nominal Ah, no causal effect or durability established; Minami archive verified. Next seek independent longitudinal controls, prevention vs recovery, compare resource endpoints and develop waveform accounting/retention protocol. Cleland/Mankov full texts remain inaccessible. Prior verified HEAD 9fadd9f6035bd134887279579fc62173ca4863d1. No equipment or production edits.

## S2 block2 current handoff
Read report40 and RESEARCH_ACCEPTANCE.md. C161/H85, 50/88. R19-K bounded PASS, no durable special-treatment proof. Sandia 8529 shallow-cycle bank, stable reference capacity but shorter PSOC intervals; INL full recharge conditioning; Alipour 697 screening, denominator unknown. Next R17/R18 and R03/R19 protocols, independent matched controls; no equipment/production. Prior verified HEAD 58f5226ac0c3511fd1a14b5e3585be986ce32c26.

## S2 block3 current handoff
Read report41 and RESEARCH_ACCEPTANCE.md. C164/H86, 52/88. R17/R18-K bounded PASS, no material recipe or reverse-charge benefit accepted. Hu original archived; Cattelan/Ruetschi full machine text only, figures unverified. Next finalize comparative waveform/retention analysis plan (not physical permission), then S3. No equipment/production. Previous verified HEAD 27d0735fd03b4dbbdf97a9d12597577a91cd055f.

## S2 exit / S3 current handoff
Read report42 and RESEARCH_ACCEPTANCE.md. C166/H87, 52/88. S2 done as literature/design deliverable; P gates remain open. Three scripts executed: s2_waveform_metrology.py (synthetic PASS), s3_bboxx_acquire.py (both public files HTTP403), s3_opzs_rest_screen.py (77651 matched keys, no hour-long rest). S3: primary dendrite/short evidence, independent capacity and relaxation data; no repeated BBOXX denial or four-cell model fitting. No physical/production edits. Prior verified HEAD c2d1e3b69085491e6fd2def19e6796609e179814.

## S3 block1 current handoff
Read report43 and RESEARCH_ACCEPTANCE.md. C171/H88, 54/88. R04-D/R13-K bounded PASS, Q/P gaps remain. Three manufacturer originals archived in sources/S3; Conradt source attribution corrected. Synthetic nonidentifiability only. Next independent relaxation/capacity data, R05/R06/R07/R11/R12. Prior verified HEAD 89e2e15e86e6957d7449ad1250e402ae34a76780. No physical/production edits.

## S3 block2 current handoff
Read report44 and RESEARCH_ACCEPTANCE.md. C175/H89, 55/88. Hassan/Nayyer Zenodo five files archived, two tables identical, no raw traces or independent measured labels; no external model fit. R11-K bounded PASS, P open. Next independent MAT decoder/units/time alignment, relaxation and independent reference cohort. Prior verified HEAD 35c6553f5370a598050c533cf01d067c99f6fe98. No hardware/production.

## S3 block3 handoff
Read report45 and RESEARCH_ACCEPTANCE.md. C179/H90, 56/88. Independent SciPy decoder and author mask verified, units intended mOhm, calibration and shared timestamp absent. SciPy project-local tools/.eis-scipy, no global install. R07-K documentary PASS; R06-K still OPEN. Next independent relaxation and measured-reference cohort; do not refit four cells. Prior verified HEAD b54465721e36f3e7f4db4c9d77daeb30d62f63be. No hardware/production.

## S3 exit / S4 block1 handoff
Read report46 and RESEARCH_ACCEPTANCE.md. C183/H91, 57/88. R15-Q PASS on Cao table p70 and Prasad measured cycling-duration evidence. Cao p71 text only, local download timeout; Prasad preprint DNS failed, published full HTML read. S3 deliverable complete, R05/R06/R12-K, R04-D-Q and P residual gates not closed. Continue S4 thermal lag/return-to-reference capacity, electrolyte/speciation/alloys, R01/R02/R16. Prior verified HEAD d14f8b7bb4bf2a017ede18dbc9b313c854f78690. No physical/production changes.

## S4 block2 handoff
Read report47 and RESEARCH_ACCEPTANCE.md. C187/H92, 59/88. R15/R16-K bounded PASS, R01/R02-K remain OPEN. Bača heat residuals; Jaworski original archived, 28 plate-edge locations; Pavlov2004 model electrode original text. Modern XRD/CT candidates indexed only, no new quantitative claims. Next controlled history and structure vs reversible capacity, then S5 consolidated evidence matrix and protocols. Prior verified HEAD 2c78714e14f32285ccf0c589a5767eecb3657129. No hardware.

## S4 exit / S5 handoff
Read report48 and RESEARCH_ACCEPTANCE.md. C192/H93, 61/88. R01/R02-K bounded PASS. Four originals in sources/S4 verified; no universal size or DCA threshold. S5 statement-level evidence/transfer, D09 cases including negatives, explicit residual Q/K, actionable test plans with controls and criteria; distinguish protocol PASS and physical approval, no repeated model fitting or denied downloads. Prior verified HEAD a6735a38441dd8ac66350e67ed03953684ffa84f. No production edits.

## S5 block1 handoff
Read reports49–50 and RESEARCH_ACCEPTANCE.md. C192/H93 unchanged, 62/88. E/T grades scoped, six E1 are archival facts only; eight D09 cases remain E4. R20-K PASS. Next common protocol and direction-specific annexes, explicitly track Q R04-D/R09, K R05/R06/R12 and P gaps; protocol design separate from physical permission. No production edits. Prior verified HEAD 4bef98d61f1e03f601f96b711b798c99cb435952.


## 2026-11-29 — дополнительные источники D09 от владельца
- @UklonGroup — https://web.telegram.org/k/#@UklonGroup — приоритет A: сравнительные испытания АКБ на циклирование. Искать исходные кривые, идентификаторы экземпляров, условия циклов, КТЦ, контрольные группы, отрицательные результаты и фактический конец ресурса.
- @zaryd10 — https://web.telegram.org/k/#@zaryd10 — приоритет B: по сообщению владельца, маркетинговая связь с Бережок-В1; независимо не проверена. Извлекать проверяемые измерения, отделять рекламу от эксперимента.
- @beregok7 — https://web.telegram.org/k/#@beregok7 — приоритет B: аналогичная заявленная владельцем коммерческая ориентация. Исключать двойной учёт перекрёстных публикаций.
Существующий @zaryadAKBin сохраняется. Канон D03/D07/D09 неизменен: Бережок-В1 не эталон алгоритма, но независимые качественные измерения оцениваются по существу. Новые сообщения пока не получены. Текущий коннектор поддерживает один источник; перед чтением проверить разрешённую конфигурацию, не вступать в группы и не писать сообщения, не обходить ограничения доступа. Сырые данные и сессия остаются локально. S5 приостановлен владельцем для расширения источников; 62/88, C192/H93 без изменений. Следующий этап: D09 intake, затем протоколы.

Current handoff supersedes prior access-not-tested notes: four-group v0.2.0 read-only verified, report51; 62/88 C192/H93. User D10 strict read-only; no joining, messaging, reactions, read acknowledgment or account operations. 313 unique messages and 44 discharge observations, E4. Next selective curves/earlier series and calibration metadata, then S5 protocols.

S5 report52: 255 unique extension search hits (overlap report51), Akom Standard cycles1–5 and initial 60Ah rating, Akom EFB thread14601 and earlier Tyumen AGM cycles33–45/70. Long rest/recharge/vehicle-use contrasts confounded; cycle18 EFB different current excluded. Three JPEGs downloaded local only, visual trace/calibration not validated. E4, C192/H93, 62/88 unchanged. Next author spreadsheet if accessible, trace validation then protocol consolidation.

S5 report53: Cyberpapa 500 same-author posts anchored to 105607, two Berezhok groups 288/290 unique targeted hits, 2 exact crossposts, 3 images inspected. AGM photo104582 Q67.8→90.6Ah while R10.24→10.53mΩ; 105243 excluded LiFePO4 after image check. Pavlov/Ignatova 1987 DOI 10.1007/BF01007806 supports negative plate shrinkage after 16h open circuit (not universal 17h kinetics). Beregok EFB SG table, current/T mismatch, auto-state/capacity inference and negative cases retained. E4 forum, no new gate; C192/H93, 62/88. Next remaining author UPS cohort, original article figures, older author posts and protocol consolidation.

S5 report54: 1000 earlier same-author posts (nonoverlap), Beregok 397/393 unique search hits, 11 images visually checked including exact duplicate. Five Delta FT12-105M C10 nominal105Ah paired UPS Q records (not six); all improve, 3/4 R increases. Correction report53 nominal and logger labels not durations. Same specimen 103111 partial-to12V fraction74/42.6/23.56%, paired full Q increases while partial Q falls. Additional negative and positive Beregok cases, Pavlov positive/negative plate structure and Peukert cross-check. E4 observations; C192/H93, 62/88. Next missing sixth, earlier author/trace acquisition then protocols.
