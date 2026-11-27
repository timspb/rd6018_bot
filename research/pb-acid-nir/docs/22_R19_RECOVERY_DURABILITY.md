# R19 — Устойчивость восстановления свинцово-кислотных АКБ
Дата: 2026-11-28. Статус: PARTIAL — литература, временные ряды и методика durability assessment; физические испытания не проводились.
Область: сколько сохраняется прирост Ah после восстановления; что известно о циклическом и календарном ресурсе; какие исследования действительно содержат повторные измерения, а какие только обещают «продление срока службы».
Ограничения проекта: никаких намеренных переполюсовок, инверсии зарядного тока, вскрытия VRLA, повышенных уставок или экспериментов на рабочем RD6018/БВ-600. Сопоставление методов не означает одобрение зарядного метода.

## I. Термины — что именно означает «восстановление держится»
1. **Immediate recovery** — измеренная ёмкость после обработки и одного стандартизованного полного заряда. Не доказывает, что материал или ресурс восстановлен.
2. **Short-cycle retention** — сохранение измеренной ёмкости в ограниченной серии циклов (например, 40). Не равно числу циклов до конца срока службы.
3. **Cycle life / EFC** — число полных эквивалентных циклов до заранее заданного критерия конца службы, с учётом throughput Ah/Wh, глубины разряда и температур.
4. **Calendar retention** — изменение при хранении/эксплуатации во времени независимо от количества EFC.
5. **Functional durability** — совокупность C20, CCA/пусковой способности, charge acceptance, pulse resistance, саморазряда, газовыделения/водопотерь и теплового поведения. Один SOH-процент или одно Rdc не описывают все эти свойства.
6. **Restored ≠ new** — улучшение относительно собственного T0 не означает возврат к исходному паспортному состоянию. Восстановленная батарея может иметь больше Ah, но оставаться ограниченной коррозией решётки, потерей воды, осыпанием PAM, мягким КЗ и разбалансом.

## II. Главная находка: опубликованы два 40-cycle follow-up, но это ещё не долгосрочный ресурс

### S01 — Karami, Masoomi, Asadi (2009), inverse charge
Полный оригинальный PDF: sources/R18/Karami_Masoomi_Asadi_2009_Inverse_Charge.pdf; DOI 10.1016/j.enconman.2009.01.010; Energy Conversion and Management 50 (2009), 893–898.
В разделе 3.4 авторы действительно сообщают, что восстановленная батарея прошла **40 циклов заряд-разряд** и сравнивалась со свежей батареей аналогичной сборки. Авторы формулируют результат как «cycle endurance 80% of the freshly battery or more» и делают вывод о пригодности повторного использования. Это важное дополнение к первому разбору R18: 40 циклов не были упомянуты в прежнем кратком выводе C81.
Критические пробелы: не определено, что именно значит 80% endurance (средняя/последняя ёмкость, нормированная к новой, или иная метрика); не приведены в тексте раздела число циклов до EOL, порог EOL, числовой ряд каждой точки, вариабельность и точное n в cycle-life test; раздел называет recovered battery в единственном числе, затем recovered batteries во множественном. Это **40-цикл comparative screening**, а не доказательство «долгого ресурса» в годах или ресурса до заранее определённого EOL.
Ключевая независимая оговорка R18 остаётся: основное восстановление 5 батарей включает замену электролита, глубокий разряд, inverse charge и обычный последующий заряд. Эффект именно обратного заряда не изолирован.

### S02 — Lee, Wong, Lim (2023), high-voltage restoration
«A Novel Approach Using High Charging Voltage for the Restoration of Discarded Lead Acid Batteries», Energies 16(4), 1598, DOI 10.3390/en16041598; полный machine-readable web text через ResearchGate/MDPI, CC BY 4.0; локальное скачивание PDF получило HTTP 403, поэтому архив отсутствует.
Авторы сообщают 40 циклов для восстановленных элементов и сравнение с новым элементом той же спецификации. В test section: заряд 2.4 V, 0.1C, cutoff 1.75 V, разряд 5-hour rate. Средняя разрядная ёмкость восстановленных элементов — 98.6% от новой ячейки или 91.3% от номинала; на последнем, 40-м цикле — 89% номинальной ёмкости. Новая ячейка в этом C5 тесте достигала максимум 94% nominal, поэтому нельзя требовать от recovered 100% номинала в той же серии.
**Механистически важное отрицательное наблюдение:** после 40 циклов SEM показал более гладкие поверхности обеих пластин, меньшую пористость и рост осаждённого PbSO₄; авторы сами описывают постепенное снижение поверхности и способности к обмену электронами. Следовательно, сохранение 89% номинала на 40-м цикле сосуществует с продолжающейся структурной деградацией.
Ограничения: cycle test — extracted 2V laboratory cells, а не intact automotive 12V battery; cells изготовлены из пластин, в beaker 160 mL 32% H₂SO₄. Для case 3 исходные элементы были взяты из четырёх retired 12V/3.5Ah VRLA; в cycle-life section число восстановленных элементов явно не указано, wording plural, Figure 12 caption — singular «new cell and recovered cell». Нет многомесячного календарного follow-up и не описан ресурс до EOL. Метод high-voltage charge — **не inverse charge Karami**, результаты нельзя объединять как одну технологию и переносить на Ca/Ca, EFB, AGM автомобильной батареи.
Отдельный safety/data point: в статье описан заметный расход 4 mL электролита за 20 h при более высоком варианте зарядки; авторы сочли его чрезмерным. Это не уставка для повторения и не доказательство безопасности «высокого напряжения».

## III. Временной ряд, в котором улучшение частично исчезло

### S03 — Ohajianya et al. (2021), high-frequency pulse desulfator, 10 weeks
«An empirical investigation of lead-acid battery desulfation using a high-frequency pulse desulfator», Journal of Advances in Science and Engineering 4 (2021), 44–52, DOI 10.37121/jase.v4i1.140. Полный текст доступен через открытый mirror Academia; локальный оригинальный PDF не архивирован.
Четыре бывшие в эксплуатации 12V/100Ah VRLA Gel батареи (серия 48V/100Ah, использовалась в PV системе около 3 лет) подключили к pulse desulfator **одновременно с PV зарядкой**. Ёмкость разряжали C10 до 1.96V/cell, измеряли до воздействия, через 2, 6 и 10 недель. Отдельной группы «только PV/обычный заряд без desulfator» не было.
По авторскому тексту относительно начального измерения:
| АКБ | После 2 недель | После 6 недель | После 10 недель |
|---|---:|---:|---:|
| B1 | +44.4% | +89.5% | +59.1% |
| B2 | +38.0% | +75.9% | +14.1% |
| B3 | +1.6% | −0.5% | −20.1% |
| B4 | +1.4% | −6.4% | −27.7% |
Таким образом, максимум у B1/B2 достигнут на 6-й неделе, а к 10-й неделе прирост заметно уменьшился; B3/B4 на 10-й неделе оказались ниже собственного baseline. Авторы указывают на возможную зависимость от положения батареи в последовательном банке и предполагают, что продолжение воздействия могло привести к пересушиванию электролита из-за overcharge; также рассматривают слишком большую нагрузку/глубину разряда для старых батарей. Причинность не установлена.
Это не доказывает, что pulse desulfator вызывает ухудшение: отсутствуют matched controls, одновременная PV зарядка, всего 4 образца и разное начальное состояние. Но исследование показывает, почему одного post-treatment Ah недостаточно: **изменение может быть неодинаковым и немонотонным уже в пределах 10 недель**.

## IV. Измеренный прирост без последующего доказательства ресурса

### S04 — Shi, Ferone, Rahn (2012), pressure-feedback desulfation
«Capacity Recovery of a Sulfated Lead-Acid Battery Using Pressure Feedback Charging Control», ASME DSCC 2012, DOI 10.1115/DSCC2012-MOVIC2012-8584. Диссертация Ying Shi архивирована локально: sources/R19/Shi_Ferone_Rahn_2012_Pressure_Feedback.pdf, SHA256 в sources/R19/SHA256SUMS.txt.
Один VRLA элемент из батареи, ранее cycle-tested to failure, подвергли low-current desulfation четырьмя этапами суммарно 313 h при среднем 0.2 A с pressure feedback. Ёмкость элемента выросла с 39.9 до 56.3Ah (+41%), но после обработки составляла лишь 64.0% номинала 88Ah. Первые два этапа суммарно 169 h дали почти весь прирост (+15.6Ah); последние два этапа добавили только 0.7Ah (~1.3%), то есть diminishing returns наступили раньше завершения 313 h. Для всей батареи диссертация приводит рост с 40Ah до 52.4Ah; авторы округляют его как +30%, но арифметика по указанным значениям даёт +31.0% — discrepancy сохранён. После десульфатации элемент легче входил в газовыделение. Длительного post-recovery cycle-life или календарного наблюдения нет. Companion paper Shi, Ferone and Rahn, «Identification and remediation of sulfation in lead-acid batteries using cell voltage and pressure sensing», Journal of Power Sources 221 (2013), 177–185, DOI 10.1016/j.jpowsour.2012.08.013, относится к той же экспериментальной линии, а не к независимой репликации; по cell voltage/pressure data авторы диагностировали одну sulfated cell и ещё три dehydrated cells. Это дополнительно показывает, что батарейный прирост был ограничен другим aging в остальных элементах. Это пример **capacity recovery with residual aging and gas risk**, не доказательство срока службы.

### S05 — Tao et al. (2021), resonance restoration
«The proactive maintenance for the irreversible sulfation in lead-based energy storage systems with a novel resonance method», Journal of Energy Storage 42 (2021), 103093, DOI 10.1016/j.est.2021.103093. В доступном тексте/аннотации заявлены среднее снижение импеданса 23% и рост ёмкости 8.6%; долгосрочная post-treatment циклическая или календарная кривая не приведена в доступном материале. Не использовать заявление «lifecycle management» как эквивалент фактически измеренного продлённого ресурса.

### S06 — Al Zyoud, Abu Elhaija (2019), cycle recovery charging (CRC)
«Solar power lead battery storage solution using cycle recovery charging method», Journal of Energy Storage 25 (2019), 100843, DOI 10.1016/j.est.2019.100843. Доступны abstract и части текста. Описаны used 12V/97Ah Gel и отдельная группа 12V/60Ah AGM; в методике группы отличаются и химией, и номинальной ёмкостью, поэтому не являются matched control для друг друга. Доступный фрагмент не позволяет установить стандартизованный долгосрочный endpoint, число циклов до EOL или календарный срок после восстановления. Утверждение о продлении shelf life не заменяет числовой durability dataset.

### S07 — Hamdan et al. (2025), hybrid CRC
«Sustainable battery storage: A hybrid charging solution», Results in Engineering 25 (2025), 103843, DOI 10.1016/j.rineng.2024.103843. Abstract-only/metadata. Заявлена переработка 24 ячеек 2V/300Ah GFM в 48V банк; только одна из 24 потребовала замены; reported +2.4% voltage и +2.2% capacity. В доступной аннотации нет явного числа циклов, календарного периода, capacity-vs-time, критериев EOL или raw dataset. Поэтому это интересное крупное число объектов, но пока **не доказательство многолетнего ресурса**.

### S08 — Radwan et al. (2025), forklift algorithm
«Improved the performance of automotive forklift lead-acid battery using a novel charging algorithm», Case Studies in Thermal Engineering 76 (2025), 107332, DOI 10.1016/j.csite.2025.107332. В abstract заявлены 12-cell/620Ah industrial battery, среднее снижение внутреннего сопротивления 57.4%, рост SG 3.75%, OCV 12%, on-load voltage 3.8%. Доступный abstract не даёт цикла до EOL или календарной кривой; internal resistance/SG/OCV improvements не заменяют capacity-retention test. Full text пока не проверен.

## V. Что значит реальный долгосрочный тест: benchmark PNNL (не исследование восстановления)

### S09 — Shamim et al. (2022), 18–28 months and 289–728 EFC
«Valve Regulated Lead Acid Battery Evaluation under Peak Shaving and Frequency Regulation Duty Cycles», Energies 15(9), 3389, DOI 10.3390/en15093389; PNNL-SA-170871. Полный PDF локально архивирован: sources/R19/Shamim_Viswanathan_2022_Energies_3389_PNNL.pdf, SHA256 в sources/R19/SHA256SUMS.txt.
Четыре одинаковых C&D SHC 12-200FT AGM lead-carbon modules, 172Ah C10, по одному модулю на каждый duty cycle. Наблюдение 18 месяцев для трёх duty cycles и 28 месяцев для одного. Получено 289, 362, 494 и 728 100%-DOD equivalent cycles (EFC) для четырёх профилей. Capacity reference test выполнялся ежемесячно (примерно каждые 58 peak-shaving или 30 frequency-regulation циклов); pulse resistance — каждые два месяца (116 PS / 60 FR циклов).
Результаты: в peak-shaving профилях после начального снижения ёмкость частично восстановилась; авторы рассматривают improved wetting, rearrangement of active material, electrolyte redistribution и возможное reversal of sulfation как гипотезы. Frequency-regulation профили деградировали сильнее; после четырёх месяцев хранения fully charged без эксплуатации у FR 57–37% отмечен резкий спад capacity, вероятно связанный с sulfation. Это **не восстановление старой батареи**, а пример того, как нужно измерять calendar/cycle aging и почему capacity trajectory бывает немонотонной.
Переносимость ограничена: AGM lead-carbon stationary modules, n=1 на каждый duty profile; не автомобильная Ca/Ca 72Ah и не matched restoration trial. Но как пример измерительного дизайна это значительно сильнее, чем 40 циклов без длительного наблюдения.

## VI. Стандартная рамка для 12V стартерной АКБ

### S10 — IEC 60095-1:2018, corrected version 2026-02
Официальный preview: sources/R19/IEC_60095-1_2018_Corrected_2026_Preview.pdf, SHA256 в sources/R19/SHA256SUMS.txt. Документ применим к 12V lead-acid starter batteries для легковых/коммерческих автомобилей. В contents указаны: 20-hour capacity check, reserve capacity, cranking performance, charge acceptance, charge retention, endurance; также optional endurance cycle test для passenger-car batteries до 100Ah. Leoch Ca/Ca 72Ah входит в диапазон по ёмкости при условии, что это стартерная АКБ соответствующей области применения.
Доступен только официальный preview/TOC, не полный текст стандарта; конкретные цикловые параметры не переписывались и не воспроизводились. Стандарт используется как reference framework, а не как самостоятельно выдуманный режим. 2026-02 corrigendum уже включён в локальный preview.

## VII. Telegram: что есть и чего нет
Локальный read-only срез @zaryadAKBin: 1800 последних сообщений из ориентировочно 92940, а не полная история.
- TG-02 из TELEGRAM_TRIAGE_001.md: одна AGM — после Repair 23Ah, после обычного заряда ИБП 25Ah; разные/неустановленные условия повторных разрядов, нет matched control и нет последующего календарного наблюдения. Это отрицательное/нейтральное наблюдение, не доказательство превосходства обычного заряда.
- Пост 105969 (ответ на 105966) утверждает, что после глубокого разряда ёмкость «никогда не восстановить», но не приводит измерений или follow-up.
- Пост 105681 об АКОМ 2022/2023 «живой» не содержит C20/CCA/истории восстановления.
- Пост 105299 описывает изменение поведения старой АКБ по сезонам/лету, но не вмешательство и не стандартизованную ёмкость.
В просмотренном срезе не найдено независимого кейса восстановления с исходным C20, описанным методом, одинаковым контрольным зарядом и повторными C20/CCA через месяцы. Это только ограниченный срез; не экстраполировать на всю группу. Новых запросов ко всей истории не выполнялось.

## VIII. Сводная оценка доказательности
| Источник | Follow-up | Что можно заключить | Главный предел |
|---|---|---|---|
| Karami 2009 inverse charge | 40 cycles | Есть краткий cycle comparison; авторы заявляют ≥80% cycle endurance к fresh | Не определён endurance metric, n и EOL |
| Lee 2023 high-voltage restoration | 40 cycles | 91.3% rated mean, 89% rated at cycle 40 | Extracted 2V cells; unclear n; morphology worsened |
| Ohajianya 2021 pulse | 10 weeks | Non-monotonic time course, часть образцов теряет прирост | n=4, PV charge co-intervention, no controls |
| Shi 2012 pressure feedback | 313h treatment, then immediate capacity | +41% on one cell, still ~64% nominal | No post-recovery cycle/calendar test |
| PNNL 2022 untreated aging benchmark | 18–28 months; 289–728 EFC | Shows robust durability monitoring and duty-cycle effects | Not a restoration experiment |
| CRC 2019 / CRC 2025 | abstract/sections only | Recovery method studied on Gel/GFM systems | No accessible standardized life curves |
| Resonance 2021 / forklift 2025 | immediate metrics | Initial C/R/IR improvements reported | No verified long-term follow-up in accessible sources |

**R19 key conclusion:** two 40-cycle studies show that an immediate recovery effect can survive at least a limited screening series under their specific conditions. One reports ≥80% undefined endurance relative to new; another reports 89% nominal capacity at cycle 40 but simultaneously documents loss of plate porosity. A separate 10-week pulse study shows the initial capacity improvement can peak and then partly disappear, with some samples falling below baseline. There is still no controlled multi-month/multi-year trial of inverse-charge recovery on modern automotive Ca/Ca/EFB/AGM batteries with matched standard-charge controls and independent capacity/CCA/EOL measurements.

## IX. Практический протокол будущей проверки — проект, не разрешение на физический опыт
1. **Population & stratification:** separate by chemistry (Ca/Ca, EFB, AGM, Gel), construction, age, lot, storage history, baseline SOH and failure mode. Do not pool one Gel with one AGM.
2. **Matched control:** standard manufacturer-approved CC/CV charge-only arm vs candidate recovery arm, randomized/blocked by initial C20 and impedance. Define n from variance/effect size and power calculation; no single specimen presented as a group result.
3. **T0:** after same full-charge and rest procedure, record C20 (or applicable standardized capacity), CCA for starter battery, pulse resistance, self-discharge, per-cell voltage if safe access exists, SG only for serviceable flooded batteries, battery temperature and mass. For sealed VRLA do not open or measure electrolyte by destructive methods.
4. **Calendar follow-up:** repeat nondestructive observations and controlled capacity/CCA checkpoints after fixed rest intervals (e.g. 1, 7, 30, 90 days) with controlled temperature. Keep storage SOC and temperature history recorded. These are proposed checkpoints, not a standard.
5. **Cycle follow-up:** define application duty, DOD/SOC window, charge completion, temperature and EFC before start. Track cumulative Ah/Wh, not only cycle count. Recheck capacity and pulse resistance at predeclared intervals. A 40-cycle screen is not lifetime qualification; continue until predefined EOL or representative service interval.
6. **Safety/degradation:** monitor ∆T, voltage imbalance, gas/pressure where non-invasive measurement exists, electrolyte mass/SG and water loss only on serviceable flooded laboratory samples; monitor VRLA mass, temperature and electrical indicators without opening. Stop at manufacturer limits or anomaly; do not provoke cell reversal, overcharge, gas accumulation or thermal runaway.
7. **Statistics:** report individual trajectories, median/mean and uncertainty, dropouts and failures, baseline-normalized retention vs both calendar time and EFC. Count capacity-test discharges in throughput. Distinguish C20, CCA, charge acceptance, internal resistance and self-discharge; they are not interchangeable.
8. **Acceptance:** pre-register the application-specific EOL and minimum retention. Do not use 80% as a universal pass criterion unless the applicable product/standard explicitly defines it. Compare restored arm against matched standard-charge control, not just its own before/after value.
No physical protocol executed. No charge settings from papers copied into RD6018.

## X. C84–C90 and H54–H59
C84 — Karami et al. (2009) report 40 charge-discharge cycles and ≥80% cycle endurance relative to a fresh similar battery; metric, n and EOL are not defined in the accessible section. R19-S01.
C85 — Lee et al. (2023) report 40-cycle recovered 2V-cell test: average discharge 91.3% nominal / 98.6% of new, cycle 40 at 89% nominal; SEM after testing shows lower porosity and sulfate accumulation. R19-S02.
C86 — Ohajianya et al. (2021) report 10-week time series: at 10 weeks B1/B2 remain +59.1/+14.1% vs baseline, B3/B4 are −20.1/−27.7%; no control and PV charging co-intervention, so causal effect of desulfator unresolved. R19-S03.
C87 — Shi et al. (2012) show +41% capacity in one desulfated VRLA cell after 313h, but final 56.3Ah vs 88Ah nominal and no post-recovery life test; the recovered cell gassed more readily. R19-S04.
C88 — PNNL 2022 demonstrates a stronger durability measurement pattern: four AGM modules, 18–28 months, 289–728 EFC, monthly capacity and bimonthly pulse-resistance reference tests; this is an aging benchmark, not proof of a restoration method. R19-S09.
C89 — No accessible controlled multi-month/multi-year inverse-charge recovery trial on modern automotive Ca/Ca/EFB/AGM with matched standard-charge controls and independent C20/CCA/EOL follow-up was found in this R19 review.
C90 — IEC 60095-1:2018 corrected 2026-02 provides the applicable 12V starter-battery test framework including 20h capacity, reserve capacity, cranking, charge acceptance, retention and endurance; optional cycle endurance test covers passenger-car batteries up to 100Ah. R19-S10.
H54 — Initial Ah recovery overstates durable benefit when water loss, gas evolution, active-mass shedding or plate porosity loss are not measured; test with matched repeated data.
H55 — Capacity response after restoration is non-monotonic and depends on initial defect and charging environment; R19-S03 is suggestive but confounded.
H56 — Calendar time and storage SOC/T explain variance not captured by cycle count alone; verify in restored matched samples.
H57 — A multi-metric durability vector (C20, CCA, pulse R, self-discharge, gas/water, ∆T) discriminates usable recovery from transient Ah rise better than a single capacity reading.
H58 — 40-cycle screens can identify early collapse but cannot reliably rank multi-year life; test by comparing cycle-40 ranking with 18–24 month/EOL outcomes.
H59 — Chemistry-matched controls are essential: Gel, AGM, GFM, Ca/Ca and EFB outcomes should not be pooled into a universal recovery percentage.

## XI. R19 status and next work
R19 = PARTIAL. Evidence of short-cycle retention exists, but no robust multi-year post-restoration proof for the target automotive chemistries. Main remaining gap is independent matched longitudinal data, not another immediate post-charge measurement.
R20 can synthesize the verified conclusions, evidence grades and no-go boundaries, preserving all unresolved hypotheses. R20 does not imply hardware implementation or approval of a recovery recipe.
