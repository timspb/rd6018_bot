# Чек-лист научной приёмки v1.1 — 28.11.2026
Дополняет ROADMAP.md, не меняет D07/D08/D09. Утверждение владельца: детализировать план и перейти к длительным спринтам. Схема оценки разработана исполнителем, веса одинаковые; это показатель исполнения работ, не доля истинных научных гипотез и не готовность ЗУ. 22 направления × 4 бинарных критерия = 88. D — документ и первичное покрытие; Q — хотя бы один релевантный количественный первичный результат с идентифицируемым методом (для R00 инфраструктурный аналог; для R11 нормативный протокол, явно не опыт); K — закрытие главного вопроса через критическую матрицу и границы переносимости, допускается обоснованный отрицательный или UNKNOWN с документированным поиском и конкретным пробелом; P — проверяемый протокол последующих работ с контрольными группами/метрологией/критериями (для R00 воспроизводимость). P не означает разрешение физического опыта. PASS не повышается от числа отчетов. OPEN — критерий не принят, возможно частично выполнен; evidence указано рядом. Начальный консервативный аудит существующих отчетов и checkpoint, не повторное чтение всех PDF. K/P не закрываются по одному черновику. D принят по наличию и предмету отчетов. Q засчитан только по явно указанным проверенным числам/нормативной процедуре; отсутствие PASS не означает отсутствие научных публикаций. Ревизии критериев версионировать; не менять знаменатель незаметно. Физическая валидация отдельной строкой, не засчитывается за литературный этап.

| ID | Тема | D | Q | Свидетельство Q или задача | K | Критерий K | P | Критерий P |
|---|---|---|---|---|---|---|---|---|
| R00 | Канон и библиотека | PASS (00_CANON.md) | PASS | 00_CANON, ROADMAP, RUNBOOK; проверка экспорта d1253f88 | PASS | Сохранены D07/D08/D09, уровни доказательности | PASS | Handoff и проверяемый GitHub snapshot |
| R01 | Зарядоприёмность/стратификация | PASS (03_R01.md) | PASS | 34_S1_CHARGE_STRATIFICATION_OPZS: Kwiecien Table2 and Budde-Meiwes 2012 full machine text; figure visual limits noted | PASS | Reports34,36–37,48: independent DCA history and spatial SG comparisons; SOC/T/history vs local charge/gradient, causal proportion UNKNOWN | OPEN | DCA/SG(z) matched SOC/T, повторяемость и пределы |
| R02 | Сульфатация/рекристаллизация | PASS (04_R02.md) | PASS | Report35 Shiota 2001 EC-AFM timing, primary machine text; image resolution caveat | PASS | Reports35,41,47–48/A05: size, distribution, phase/contact/accessibility vs reversible Q, counterexamples; universal morphology threshold UNKNOWN | OPEN | Независимые химические/функциональные метки, одинаковая зарядная подготовка |
| R03 | Формы тока | PASS (05_R03.md) | PASS | NASA TM-82709 Table II, 2 cells; R20-A03 Cooper/Lam | PASS | R03/report26/report39: separate waveform, mean/net Ah, Wh/T/time, conditioning, immediate vs retention; no universal superiority, specific efficacy UNKNOWN | OPEN | Matched standard-charge control, predefined endpoints и resource guardrails |
| R04-D | Дендриты | PASS (06_R04_DENDRITES.md) | OPEN | Полный первичный опыт с доказанным металлическим мостиком, не только растворимость | PASS | R04-D/R13/report43: distinguish metallization, mechanical/sediment contact, chemical/external losses; independent metallic continuous bridge evidence still OPEN | OPEN | Неинвазивная диагностика и независимые подтверждения без намеренного повреждения |
| R04 | Газ, коррозия, вода | PASS (07_R04_MIX.md) | PASS | Report35 Parnigotto 2022 Table1 nine-lot measured normalized water loss; no causal isolation | PASS | Reports35–38: separate gas/recombination/corrosion and water; flooded vs VRLA transfer bounded, absolute thresholds UNKNOWN | OPEN | Проверяемые критерии риска и остановки, паспорт конкретной модели |
| R05 | Релаксация | PASS (08_R05_RELAXATION.md) | PASS | R20-A09 original Digatron: 31 four-hour rest traces | OPEN | Разделить поляризацию, T, SOC, градиент; независимые данные и воспроизводимость | OPEN | Фиксированные окна покоя и нагрузок, погрешность, диагностическая неопределенность |
| R06 | Импеданс | PASS (09_R06_IMPEDANCE.md) | PASS | A06/A07/report45: 2104 spectra, independent decoder and mask verified; intended mOhm established | OPEN | Decoder/mask and intended scale verified report45; external raw cohort, exact chronology and independent calibration still OPEN | OPEN | Валидность, повторяемость, matched SOC/T, критерий отказа от оценки |
| R07 | Дифференциальная диагностика | PASS (10_R07_DIFFERENTIAL.md) | PASS | R13 Conradt full text; R20-A05/A10 independent constraints | PASS | R07/reports28–33,43–45: alternative mechanisms, independent functional/physical labels, UNKNOWN/MIXED; classifier NOT_ESTABLISHED | OPEN | Held-out батареи, sensitivity/specificity/coverage и цена ошибки |
| R08 | MAIN | PASS (11_R08_MAIN.md) | PASS | Sandia Stevens/Corey Fig1/2, Ah in/out; проверенная арифметика | PASS | R08/report35/report38: tail, CF, actual CV, independent functional capacity; model-specific full-SOC accuracy UNKNOWN | OPEN | Модель-специфичный критерий завершения, ложные окончания, контроль Q/T |
| R09 | MIX | PASS (12_R09_MIX_CRITERIA.md) | OPEN | Mamadou C&D полный протокол/данные; прямой SG(z) и водный баланс | PASS | Reports R09,34–37: separate bulk gradient, inter-cell equalization, functional charge; D09 claims not independently replicated; specific MIX UNKNOWN | OPEN | Условный протокол только в пределах спецификаций; независимые SG(z), Q, T/вода |
| R10 | Десульфатация | PASS (13_R10_DESULFATION.md) | PASS | R20-A03/A04 Lam/Bopp/Hund original figures and outcomes | PASS | R10/R19/A03/A04/report38: matched ordinary charge, uncertainty, damage exclusion; durable treatment-specific efficacy UNKNOWN | OPEN | Порог минимального значимого эффекта до опыта, повторный Q и retention |
| R11 | C20/Пейкерт | PASS (14_R11_CAPACITY_PEUKERT.md) | PASS | IEC 60095-1:2018 protocol; A07 raw residual Q (не C20) | PASS | R11/report44: IEC corrected2026 scope, rate/T/cutoff and load history, CC vs CR, uncertainty; full procedure and actual metrology remain open | OPEN | Метрология/traceable интеграл, повторяемость, отдельные C10/C20/CCA |
| R12 | SOC/SOH | PASS (15_R12_SOC_SOH.md) | PASS | A06–A10 grouped residual Q, direct Urest counterexample | OPEN | Внешняя выборка независимых fully charged C20; baseline/coverage | OPEN | Замороженный прогноз, интервалы, held-out physical batteries |
| R13 | Саморазряд/мягкое КЗ | PASS (16_R13_SELF_DISCHARGE_SHORTS.md) | PASS | Conradt 2024 primary full text pp82–93, limits noted | PASS | R13/report43: separate chemical/external loss, relaxation and short; independent retention and physical labels required; specific diagnosis UNKNOWN | OPEN | Наблюдение покоя и внешней нагрузки, без создания дефекта; критерий UNKNOWN |
| R14 | Ca/Ca/EFB/AGM/GEL | PASS (17_R14_CONSTRUCTION_CACA_EFB_AGM_GEL.md) | PASS | Report36 Bauknecht 2022 Table A1 four EFB variants and cell geometry; rank reversal | PASS | R14/R16/R17/reports36–38: alloy, electrolyte, gas exchange, NAM/PAM, duty and transfer separated; universal ranking UNKNOWN | OPEN | Отдельные профили/пределы применимости, без общей уставки |
| R15 | Температура | PASS (18_R15_TEMPERATURE.md) | PASS | Report46: Cao2015 same-model repeated Q(T) Table8 p70 visually checked; Prasad2023 cycle durations, percentage inconsistencies retained | PASS | Reports46–47/R15: distinguish Q(T), ageing, heat generation/storage/loss, internal vs ambient T; universal correction and core mapping UNKNOWN | OPEN | Термометрия, стабилизация, допустимые диапазоны и неопределенность |
| R16 | Электролит/сплавы | PASS (19_R16_ELECTROLYTE_ALLOYS.md) | PASS | NBS RP1165, original archive + r16_nbs_solubility_analysis.py | PASS | R16/report47: distinct solubility/speciation, conductivity, PAM/NAM and alloy/interface/life; no universal composition or recovery benefit | OPEN | Модельная лабораторная программа, без вмешательства в АКБ |
| R17 | Углерод/NAM/PAM | PASS (20_R17_CARBON_ACTIVE_MASS.md) | PASS | Первичные открытые PDF + r17_quantitative_provenance.py | PASS | R17/reports36,40,41: carbon dose and structure, NAM/PAM, DCA/HER/water/corrosion, opposite effects; optimal material UNKNOWN | OPEN | Материалы/производство/ресурс, отдельно NAM и PAM; не retrofit |
| R18 | Переполюсовка | PASS (21_R18_POLARITY_REVERSAL.md) | PASS | R18 primary source review, R19 Lee 2023 40-cycle series | PASS | R18/R19/report41: separate electrode potential, cell and pack reversal; accidental survivability and bundled restoration do not establish durable efficacy | OPEN | Наблюдение имеющихся архивных событий; без намеренной инверсии |
| R19 | Устойчивость восстановления | PASS (22_R19_RECOVERY_DURABILITY.md) | PASS | R20-A03/A04 Lam, Bopp, Hund; R19 longitudinal outcomes | PASS | R19/reports26–27/40: separate immediate, retention, functional EFC/calendar and EOL; ordinary-charge comparator; durable superiority NOT_ESTABLISHED; censored outcomes explicit | OPEN | Протокол retention и заранее заданный минимальный полезный эффект |
| R20 | Синтез и доказательность | PASS (23_R20_SYNTHESIS.md) | PASS | A06–A10 raw data and executed grouped baseline, external admission | PASS | Reports49–50: C01–C192 E/T matrix, D09 eight cases, negative and unknown evidence, bounded transfer | OPEN | Консолидированная программа/рекомендации D08 только по подтвержденным выводам |

## Исходное состояние
PASS 39/88 (44.3%). D 22/22; Q 15/22; K 1/22; P 1/22. Исходные ROADMAP DONE 1/22, PARTIAL 21/22, не изменены. Лабораторная приёмка собственных физических опытов: 0; отдельное разрешение и протокол.

## Длительные спринты — порядок и конечные результаты
S1 — зарядная электрохимия и критерии (R01,R02,R04,R08,R09,R10,R14): извлечь первичные методы, сопоставить DCA/SG(z)/газ/Q, провести ограниченную архивную проверку OPzS A11 как независимого источника зарядной предыстории/неоднородности; сопоставить R08/R09 с D09 наблюдениями, выпустить матрицу критериев с границами. Не выдавать модельную уставку за рекомендацию.
S2 — восстановление/формы тока/ресурс (R03,R17,R18,R19): matched controls, Ah/Wh/T/EFC/calendar, открытые пробелы Cleland/Mankov, современные исследования и практические отрицательные случаи.
S3 — диагностика/метрология (R04-D,R05,R06,R07,R11,R12,R13): OPzS тестовые эпизоды и независимые источники; BBOXX staged telemetry — event labels, не C20; к EIS не возвращаться для бесконечного подбора на четырех ячейках.
S4 — материалы и среда (R15,R16,R17,R14): температура, электролит, сплавы, NAM/PAM, матрица переноса.
S5 — итоговый синтез (R20): поутвержденческая матрица E/T, D09, перечень подтвержденных/отрицательных/UNKNOWN, протоколы, адресные научные рекомендации D08 (не реализация).
Внутри каждого спринта продолжать следующие независимые подзадачи без остановки на промежуточном отчете; checkpoint и хеш-проверка в конце содержательного блока. Если источник недоступен — фиксировать и переходить к другим доказательствам. Не создавать новые спринты ради счетчика, не изменять аппаратное обеспечение. Длительная работа ограничена текущим запуском; нельзя обещать автономный прогресс после ответа без реально подключенного механизма. При следующем обращении возобновить по checkpoint, не повторять работу.

## S1 checkpoint 28.11.2026
Current PASS 40/88 (45.5%), D22 Q16 K1 P1. R01-Q advanced on two quantitative primary reports (report 34). Initial 39/88 remains historical baseline. No other gate promoted; physical validation remains separate. S1 in progress; R09 full protocol still open.

## S1 block 2
Current PASS 43/88 (48.9%); D22 Q19 K1 P1. R02-Q/R04-Q/R14-Q admitted from reports35–36. R09-Q and all remaining K/P stay OPEN; critical matrix is draft, not model-specific validation.

## S1 block 3
Current PASS 44/88 (50.0%); D22 Q19 K2 P1. R09-K documentary distinction accepted after cross-check of R09 and reports34–37; R09-Q/P remain OPEN, physical validation separate. Earlier progress rows historical.

## S1 block 4 / transition
Current PASS 48/88 (54.5%); D22 Q19 K6 P1. R04/R08/R10/R14 K bounded documentary accepted; report38 includes evidence matrix and remaining UNKNOWN. S1 deliverable completed, unresolved gates remain OPEN; no physical or firmware acceptance. R01-K/P, R02-K/P, R04-P, R08-P, R09-Q/P, R10-P, R14-P carry forward, with materials work in S4 and protocol synthesis S5. S2 next; no change to denominator or original roadmap DONE/PARTIAL.

## S2 block 1
Current PASS 49/88 (55.7%); D22 Q19 K7 P1. R03-K bounded documentary accepted after NASA/Lam/Cooper/James/Minami/D09 review. R03-P and R19-K/P remain OPEN. No change in denominator or physical acceptance.

## S2 block 2
Current PASS 50/88 (56.8%); D22 Q19 K8 P1. R19-K bounded documentary accepted from R19/A03/A04 and report40. Specific durable restoration UNKNOWN, R19-P OPEN; no denominator change or physical acceptance.

## S2 block 3
Current PASS 52/88 (59.1%); D22 Q19 K10 P1. R17-K/R18-K bounded documentary accepted; R17-P/R18-P/R03-P/R19-P remain OPEN. S2 comparative design constraints recorded; actual sample size, calibrated metrology and model-specific limits unresolved. No change to denominator or physical acceptance.

## S2 exit / S3 admission
Current PASS 52/88 (59.1%); D22 Q19 K10 P1 unchanged. S2 main deliverable completed (reports39–42), R03/R17/R18/R19 P open pending model-specific metrology and validation; S3 begun. No valid hour rest in strict OPzS screen, no BBOXX telemetry downloaded. No criterion promoted for synthetic tests or absent data.

## S3 block 1
Current PASS 54/88 (61.4%); D22 Q19 K12 P1. R04-D-K/R13-K bounded documentary accepted, R04-D-Q remains OPEN because continuous metallic bridge independently phase/conductance verified not established; no P advanced. Conradt attribution corrected. No physical acceptance.

## S3 block 2
Current PASS 55/88 (62.5%); D22 Q19 K13 P1. R11-K bounded documentary accepted; R11-P remains open. SOH plot-only data not admitted as external validation; no R12-K promotion. Independent MAT decoder/timestamp/units still unresolved. No physical acceptance.

## S3 block 3
Current PASS 56/88 (63.6%); D22 Q19 K14 P1. R07-K bounded documentary accepted; R06 decoder/mask/units subtasks done but R06-K remains OPEN for external cohort/chronology/calibration. R05/R12-K and P gates remain open. No physical acceptance.

## S3 exit / S4 block 1
Current PASS 57/88 (64.8%); D22 Q20 K14 P1. R15-Q accepted on visually verified temperature-capacity data and published cycling-duration evidence; R15-K/P remain OPEN. S3 main deliverable completed with R05/R06/R12-K and R04-D-Q/P residual gaps retained. No physical acceptance or denominator change.

## S4 block 2
Current PASS 59/88 (67.0%); D22 Q20 K16 P1. R15-K/R16-K bounded documentary accepted; no P advanced. R01/R02-K remain OPEN, target thermal mapping and material effects not independently validated. No physical acceptance.

## S4 exit / S5 intake
Current PASS 61/88 (69.3%); D22 Q20 K18 P1. R01-K/R02-K bounded documentary accepted; all other open gates retained. S4 main deliverable complete. S5: statement-level evidence/transfer matrix, review open Q R04-D/R09, K R05/R06/R12/R20 and P program; protocol acceptance does not require physical execution but must meet original controls/metrology/decision criteria. No denominator change or physical permission.

## S5 block1
Current PASS 62/88 (70.5%); D22 Q20 K19 P1. R20-K documentary PASS on reports49–50; Q R04-D/R09, K R05/R06/R12 and 21 P remain OPEN. No empirical acceptance or denominator change. All 93 hypotheses remain separate.


## Report59 bounded literature-pass exit
Five residual gates R04-D-Q, R09-Q, R05-K, R06-K, R12-K remain OPEN (EXPERIMENTAL_EVIDENCE_REQUIRED). Original criteria unchanged. Theoretical 61/66; total62/88. Proceed with P3/P4/P5 documentary protocols; reopen on new independent evidence, not repeated searches.
