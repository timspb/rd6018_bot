# Дорожная карта v1.0
Утверждена пользователем продолжением работ 28.11.2026. Статусы: DONE — закрыт литературный этап; PARTIAL — отчет есть, первоисточники/проверки неполны; OPEN — не начат. Лабораторная проверка отдельно.
| Этап | Тема | Приоритет | Статус | Результат |
|---|---|---|---|---|
| R00 | Канон и начальная библиотека | P0 | DONE | 00_CANON |
| R01 | Зарядоприемность и стратификация | P0 | PARTIAL | 03_R01 |
| R02 | Сульфатация и рекристаллизация | P0 | PARTIAL | 04_R02 |
| R03 | Импульсный и асимметричный заряд | P0 | PARTIAL | 05_R03 |
| R04-D | Дендритные замыкания | P0 | PARTIAL | 06_R04_DENDRITES |
| R04 | Высоковольтный дозаряд, газ, коррозия, вода | P0 | PARTIAL | 07_R04_MIX |
| R05 | Релаксация и переходные процессы | P0 | PARTIAL | 08_R05_RELAXATION |
| R06 | Импеданс, сопротивление, модели | P0 | PARTIAL | 09_R06_IMPEDANCE |
| R07 | Дифференциальная диагностика | P0 | PARTIAL | 10_R07_DIFFERENTIAL |
| R08 | Критерии MAIN | P0 | PARTIAL | 11_R08_MAIN |
| R09 | Критерии MIX | P0 | PARTIAL | 12_R09_MIX_CRITERIA |
| R10 | Десульфатация и критерии завершения | P0 | PARTIAL | 13_R10_DESULFATION |
| R11 | C20, Пейкерт, температура | P0 | PARTIAL | 14_R11_CAPACITY_PEUKERT |
| R12 | SOC/SOH без полного КТЦ | P0 | PARTIAL | 15_R12_SOC_SOH |
| R13 | Саморазряд и мягкое КЗ | P0 | PARTIAL | 16_R13_SELF_DISCHARGE_SHORTS |
| R14 | Ca/Ca, EFB, AGM, GEL | P0 | PARTIAL | 17_R14_CONSTRUCTION_CACA_EFB_AGM_GEL |
| R15 | Температурные зависимости | P1 | PARTIAL | 18_R15_TEMPERATURE |
| R16 | Электролит и легирование | P1 | PARTIAL | 19_R16_ELECTROLYTE_ALLOYS |
| R17 | Углерод и активные массы | P1 | PARTIAL | 20_R17_CARBON_ACTIVE_MASS |
| R18 | Переполюсовка и последствия | P1 | PARTIAL | 21_R18_POLARITY_REVERSAL |
| R19 | Устойчивость восстановления | P0 | PARTIAL | 22_R19_RECOVERY_DURABILITY |
| R20 | Синтез алгоритмов, evidence grades и no-go границ | P0 | PARTIAL | 23_R20_SYNTHESIS + 24_R20_EVIDENCE_GAP_AUDIT + 25_R20_LONGITUDINAL_METROLOGY + 26_R20_CONTROLLED_COMPARISONS + 27_R20_REVERSIBLE_LOSS_LIMITS + 28_R20_PCL_IDENTIFIABILITY + 29_R20_RAW_EIS_AND_LABELS + 30_R20_ZHIT_AND_CAPACITY + 31_R20_MULTIFEATURE_BASELINES + 32_R20_REST_HISTORY + 33_R20_COVERAGE_EXTERNAL_DATA + 34_S1_CHARGE_STRATIFICATION_OPZS + 35_S1_GAS_SULFATE_MAIN + 36_S1_TRANSFER_AND_MIX + 37_S1_STRATIFICATION_COMPARISON + 38_S1_COMPLETION_AND_RECOVERY_MATRIX + 39_S2_PULSE_GAS_COMPARISON + 40_S2_RETENTION_AND_RESOURCE + 41_S2_MATERIAL_REVERSAL_EVIDENCE + 42_S2_EXIT_S3_ADMISSION + 43_S3_SHORT_MECHANISMS + 44_S3_CAPACITY_SOH_PROVENANCE + 45_S3_EIS_DECODER_AND_VALIDITY + 46_S3_EXIT_S4_TEMPERATURE + 47_S4_HEAT_ELECTROLYTE_ACTIVITY + 48_S4_DCA_SULFATE_ACCESSIBILITY |
Параллельно: архив первоисточников; форумные эксперименты; диагностические случаи; метрология будущего стенда. CASE-001: наблюдение ограничено, диагноз не установлен. R20 не означает готовность к деплою.

## Детализация приёмки и длительные спринты
RESEARCH_ACCEPTANCE.md — каноническое дополнение дорожной карты, 22×4=88 критериев, начальное 39/88, после S1/A11 40/88. S1 charge chemistry → S2 recovery/resource → S3 diagnostics/metrology → S4 materials/environment → S5 synthesis. Original DONE/PARTIAL remain unchanged. Do not count physical validation in documentary score.

S1 block2: 43/88; reports 35–36. Continue S1: full controlled MIX evidence, model-specific manufacturer matrix, independent verification protocols; no premature transition to S2.

S1 block3: 44/88, R09-K documentary accepted. Next target-model documentation and metrology/controls, R01/R02/R04/R08/R10/R14 critical reviews; S1 continues.

S1 deliverable completed (reports34–38); 48/88. Open gates carried forward, no physical acceptance. Next S2 recovery/waveforms/resource R03,R17,R18,R19; matched controls, calendar/EFC retention, negative outcomes and literature gaps.

S2 block1: 49/88, R03-K accepted. Next comparative retention/aging studies and waveform accounting protocol; prevention separate from restoration, avoid model-predicted life as measured EOL.

S2 block2: 50/88; R19-K accepted. Continue R17 material/HER tradeoffs, R18 electrode/cell inversion distinction, waveform accounting and retention protocol gates; no special treatment validated.

S2 block3: 52/88; R17-K/R18-K documentary accepted. Next S2 comparative waveform/retention analysis plan and metrology checks, then S3 diagnostics. No intentional reversal or factory recipe transfer.

S2 exit / S3 admission: report42, 52/88 unchanged. S2 deliverable complete; open criteria retained. S3: R04-D,R05,R06,R07,R11,R12,R13, primary short-circuit evidence and alternative independent archives; no repeat of denied acquisition or four-cell fitting.

S3 block1: 54/88; R04-D/R13-K bounded PASS. Next R05/R06/R07/R11/R12 independent relaxation/capacity/measurement evidence and classifier limitations; no repeated denied acquisition.

S3 block2: 55/88; R11-K accepted. Next independently verify MAT decoder and impedance units/chronology; seek genuine measured-reference cohort, no training on plot-only data or repeated four-cell fitting.

S3 block3: 56/88, R07-K accepted. Independent MAT decoder/mask completed; intended mOhm scale established, exact chronology and external cohort open. Next independent relaxation/reference capacity data, no additional four-cell fitting.

S3 exit/S4 block1: 57/88, R15-Q accepted. S3 main deliverable complete, named open criteria carried forward. S4: paired temperature/recovery controls, heat balance, electrolyte/speciation and alloys, R01/R02/R16 critical matrix; no repeated four-cell fitting.

S4 block2: 59/88; R15/R16-K accepted. Next R01/R02 controlled history and structural/functional counterexamples, then S5 evidence matrix and protocol consolidation.

S4 exit/S5 intake: 61/88, R01/R02-K bounded accepted. Next S5 statement-level E/T and D09 matrix, protocol consolidation and D08 evidence-bounded recommendations; retain missing raw labels/primary evidence as explicit gaps.
