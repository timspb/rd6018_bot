# R20 — Синтез научной базы: доказательность, применимость, диагностические требования и no-go границы
Дата: 2026-11-28. Статус: PARTIAL — документальный синтез R01–R19. Это не валидированный зарядный алгоритм, не программа управления и не разрешение на физический эксперимент.
Основание: 00_CANON.md (D07/D09), ROADMAP.md, 03_R01–22_R19, CONCLUSIONS.md C01–C96, HYPOTHESES.md H01–H61, DECISIONS.md и EXPERIMENT_PROTOCOL.md.
Главный принцип: научное утверждение, диагностический вывод, применимость к конкретной конструкции, паспортное требование и решение о внедрении — разные сущности. Существующая реализация RD6018/будущего БВ-600 не является источником истины.

## 1. Результат синтеза в одном абзаце
У свинцово-кислотной АКБ нет одного надёжного скалярного признака, который одновременно устанавливает SOC, остаточную C20, пусковую способность, механизм деградации и оставшийся ресурс. PbSO₄, кислотная стратификация, кинетика заряда, температура, коррозия решёток, структура NAM/PAM, газовые реакции и внутренние утечки взаимодействуют, но ни один из рассмотренных измерительных каналов не наблюдает их все. Клеммные U/I/T, OCV, CCA, Rdc, EIS, SG и DCA отвечают на разные вопросы и имеют собственные ограничения. Успех краткого восстановления Ah не равен возврату к новой батарее или доказанному сроку службы. Поэтому допустимая логика будущего управления должна сначала оценивать качество/полноту данных, затем отдельно выдавать измеренные показатели и оценочные состояния, а при неидентифицируемом механизме — сохранять UNKNOWN/SUSPECTED, не запуская рискованный силовой режим.

## 2. Схема уровней доказательности
Уровень присваивается **конкретному утверждению**, а не статье целиком. Один источник может подтверждать измеренный результат в своём образце, но не подтверждать причинный механизм или перенос на другой тип АКБ.

| Уровень | Критерий | Что допустимо утверждать |
|---|---|---|
| E1 — прямое доказательство в области опыта | Полный первичный текст, понятны образцы/условия/методика, числовой результат извлечён и перепроверен | Только измеренный эффект для указанной конструкции и условий |
| E2 — ограниченное первичное доказательство | Полный текст, но малое n, один образец/серия, слабый контроль, короткий горизонт или неясная неопределённость | Наблюдение/механизм в пределах опыта, не универсальный алгоритм |
| E3 — косвенная опора | Abstract, indexed snippet, manufacturer document, preview, исторический стандарт или неполный текст | Библиографическая опора/спецификация/кандидат, но не независимая валидация |
| E4 — практическое наблюдение | Форум/Telegram/единичный случай без независимой методики и контроля | Гипотеза и повод искать измерения, не доказательство |
| H — открытая гипотеза | Механизм или диагностическое правило ещё не проверены | Не использовать как установленный факт |

Отдельная ось переноса:
- T1 — та же химия, конструкция, режим и измерительная методика.
- T2 — близкая конструкция, перенос требует проверки.
- T3 — другая химия/масштаб/назначение (например, 2V лабораторный элемент → 12V стартерная АКБ).
- T4 — область переноса неизвестна.

**E1 не означает T1.** Полный и качественный опыт на 2V лабораторной ячейке может иметь E1 для этой ячейки и T3 для автомобильной AGM/EFB/Ca-Ca. Паспорт производителя имеет силу для своей модели/режима, но не становится универсальным законом.

## 3. Консолидированные выводы по тематическим блокам

### 3.1. Химия разряда, сульфатация и электролит — C01–C12, C59–C66
- PbSO₄ — нормальный продукт разряда; патологическая сульфатация зависит от предыстории, размера/распределения кристаллов, транспорта, локальной концентрации и доступности активной массы. Не сводить все отказы к «крупным кристаллам» (R02).
- Растворимость PbSO₄ в H₂SO₄ нелинейна по концентрации; максимум проводимости электролита не совпадает с максимумом растворимости или оптимумом ресурса. Число из чистой воды нельзя переносить на электролит АКБ, а массовую долю H₂SO₄ нельзя путать с SG (R16).
- В acid-limited и NAM/PAM-limited конструкциях изменения SG могут давать разные эффекты по C20 и циклам. Вывод «чем выше плотность, тем лучше» не подтверждён; изменение электролита старой АКБ не является безопасным универсальным лечением (R16).
- Сульфатация, стратификация, пассивация, коррозия решётки, потеря воды и внутренний soft-short могут сосуществовать. Устранение одного симптома не доказывает устранение остальных (R07/R13/R16).

### 3.2. Зарядоприёмность, импульсы, MAIN и MIX — C02–C12, C22–C30
- DCA/CA зависит от SOC, T, предыстории, состава NAM/PAM, электролита и режима. Это transient acceptance, не C20, не CCA и не срок службы (R01/R17).
- Универсальное преимущество импульсного или асимметричного заряда не установлено. При прямоугольном токе с нулевой паузой и фиксированном среднем токе простая омическая модель даёт рост I²R потерь как 1/D; это аналитический предел, не полный тепловой баланс (R03).
- MAIN завершённость и подтверждение полного SOC — разные статусы. Малый хвостовой ток сам по себе не доказывает полный заряд, особенно при сульфатации и низкой кулоновской эффективности на высоком SOC (R08).
- Дозаряд/перемешивание/выравнивание имеют разные цели и критерии. Рост SG или исчезновение вертикального градиента не доказывают рост C20; клеммный интеграл тока не равен газовому заряду (R04/R09).
- MIX нельзя запускать только по названию химии или одному признаку. Для VRLA AGM/GEL газовый перезаряд может приводить к клапанному сбросу, необратимой потере воды и тепловой неустойчивости; универсальная MIX-уставка не выведена. Для flooded/EFB нужны подтверждение стратификации, паспорт и контроль риска (R04/R09/R14).
- Десульфатация не имеет общего критерия завершения по току или времени. Прирост C следует сравнивать с повторяемостью/неопределённостью и контрольной группой; если изменение неотличимо от погрешности, это «эффект не доказан», а не «полностью восстановлена» (R10).

### 3.3. Напряжение, релаксация, импеданс и SOC/SOH — C13–C24, C31–C39
- Напряжение после снятия тока включает остаточную поляризацию и меняется с температурой/локальной концентрацией; даже многочасовой отдых не гарантирует равновесную ЭДС. При низкой температуре релаксация в отдельных опытах превышала 100 ч (R05).
- Многокомпонентная экспоненциальная аппроксимация U(t) описывает данные, но не уникально идентифицирует механизм. При коротком импульсе A/I не равно истинному R; параметры могут быть плохо идентифицируемы (R05).
- Rdc, конечновременное DC сопротивление, 1kHz impedance, EIS и Rcharge60 — разные величины. Частота, SOC, температура, предыстория и форма возбуждения меняют связь с ёмкостью; один «внутренний R» не является универсальным SOH (R05/R06/R07).
- SOC и SOH_C связаны через неизвестную Cmax. Без независимого якоря C20 или валидированной модели обе величины нельзя достоверно получить из одного OCV/Q. CCA и проводимость не заменяют C20 (R11/R12).
- Высокая точность модели на последовательных циклах одной батареи не доказывает перенос на другие экземпляры/производителей; требуются battery-held-out validation, независимый C20 ground truth и температурная валидация (R12).
- Истинный EIS требует EIS-измерителя и протокола; Modbus U/I или один DC импульс не следует называть EIS (R12).

### 3.4. Саморазряд, мягкое КЗ и дифференциальная диагностика — C19–C21, C40–C44
- Внутренний short, нормальный саморазряд, внешняя паразитная нагрузка и постзарядная релаксация — разные процессы. Падение OCV всей 12V батареи не локализует слабый элемент и не устанавливает Ishort (R13).
- В одном лабораторном исследовании Rdc при полном SOC не исключал soft-short; чувствительность менялась с SOC. Следовательно, отсутствие аномалии одного R не закрывает гипотезу, а высокий Iend также неспецифичен (R13).
- Полевые доли отказов из выбранной выборки не являются популяционной вероятностью для другой батареи/кейса. Диагноз требует независимых labels, временного ряда U/I/T, контроля внешней нагрузки и, где безопасно доступно, побаночного напряжения (R13).
- Без достаточных данных допустимы UNKNOWN/SUSPECTED/CONSISTENT/SUPPORTED; HIGH_RISK может требовать STOP без подтверждения конкретной морфологии. Не подменять неопределённость уверенным диагнозом (R07/R13/R18).

### 3.5. Конструкция, температура и активная масса — C45–C58, C67–C75
- Ca/Ca описывает семейство сплава решётки; EFB — модифицированную flooded конструкцию; AGM/GEL — VRLA с иммобилизованным электролитом. Это разные оси, которые пересекаются, а не взаимоисключающие типы. Маркировка не задаёт алгоритм заряда (R14).
- Температура разряда влияет на доступную ёмкость, а thermal history — на необратимое старение. Температурная компенсация зависит от модели и режима (float/cycle); универсального mV/°C нет. T_surface/T_ambient не равны температуре активной массы (R15).
- Carbon в NAM может улучшать HRPSoC/DCA через проводимость, морфологию PbSO₄ и двойной слой, но дозировка/пористость имеют нелинейные эффекты; начальные DCA ранги могут терять различимость после run-in/покоя. Микроциклы HRPSoC не равны полным циклам до EOL (R17).
- PAM carbon и NAM carbon — разные задачи; возможное улучшение в отдельных рецептурах не доказывает универсальный эффект или безопасность retrofit. Рост HER/саморазряда/водопотерь и кислородный цикл VRLA — обязательные guardrails (R17).

### 3.6. Переполюсовка и восстановление — C76–C91
- Электродная инверсия, Ucell<0 под нагрузкой, отрицательное U всей батареи и обратное подключение ЗУ — разные состояния. Слабый последовательный элемент может инвертироваться при положительном Utotal; общая 12V телеметрия не показывает состояние каждой банки (R18).
- В отдельных специальных конструкциях восстановление Ah после случайной инверсии наблюдалось; это не доказывает безопасность намеренного reverse charge или многолетний ресурс (R18).
- Karami 2009 сообщает 40 cycles и ≥80% неопределённой «cycle endurance» относительно свежей батареи; Lee 2023 сообщает 40-cycle test на extracted 2V cells и 89% rated на cycle 40, одновременно фиксируя снижение пористости/рост PbSO₄. Это short-cycle evidence, не EOL/calendar lifetime (R18/R19).
- Ohajianya 2021 показывает немонотонный 10-недельный ряд без контрольной группы; часть образцов к 10-й неделе опустилась ниже исходной ёмкости. Это не доказывает причинный вред pulse desulfator, но опровергает упрощённое ожидание монотонного роста (R19).
- Нет доступного controlled multi-month/multi-year inverse-charge recovery trial на современных automotive Ca/Ca/EFB/AGM с matched standard-charge control и C20/CCA/EOL follow-up (R19).
- Устойчивое восстановление требует calendar retention + EFC/throughput + capacity/CCA/charge acceptance/self-discharge/water-loss/thermal metrics. Один post-treatment Ah или 40 cycles недостаточны (R19).

## 4. Противоречия, которые синтез разрешает
| Кажущееся противоречие | Правильное разделение |
|---|---|
| «Плотность выше — ёмкость выше» vs «плотность выше — ресурс ниже» | Начальная C20 и циклический ресурс имеют разные оптимумы; acid-limited/NAM-limited конструкции различаются (R16). |
| «Импульсы улучшают зарядоприёмность» vs «импульсы теряют преимущество» | Краткая DCA/CA и долгосрочный C20/EFC — разные endpoints; форма тока сравнивается при одинаковых Ah/Wh/T и контролях (R03/R17). |
| «После MIX плотность стабилизировалась» vs «стратификация осталась» | Средняя SG и вертикальный SG(z) — разные наблюдения; гомогенизация не гарантирует однородность активной массы (R01/R06/R09). |
| «Нормальный OCV/Rdc» vs «soft-short существует» | SOC, температура, время покоя и побаночная неоднородность могут скрывать дефект (R13). |
| «После восстановления ёмкость выросла» vs «батарея остаётся старой» | Immediate C20, 40-cycle retention, EFC-to-EOL, calendar retention и CCA/водопотери — отдельные критерии (R18/R19). |
| «Положительный опыт для carbon» vs «carbon ухудшает водный баланс» | Тип, пористость, доза, NAM/PAM, VRLA oxygen cycle и duty cycle меняют результат; нет универсальной дозы/retrofit (R17). |
| «Внешняя T нормальная» vs «локальный перегрев» | Температурное поле внутри элемента неоднородно; одна ambient точка не закрывает thermal risk (R15). |

## 5. Границы допустимых утверждений
**Можно утверждать:**
- конкретный измеренный результат конкретной публикации, если указаны образец, метод, температура, SOC/DOD, ток, cutoff, длительность и ограничение переноса;
- что DCA, C20, CCA, Rdc, EIS, SG и OCV — различные показатели;
- что отсутствие данных означает UNKNOWN, а не подтверждение или опровержение механизма;
- что рост Ah после процедуры не доказывает восстановление ресурса без повторных контрольных тестов.

**Нельзя утверждать на текущей базе:**
- универсальную уставку 16/17V, фиксированный 0.05C, длительность MIX или «один профиль для всех Ca/Ca/EFB/AGM/GEL»;
- что импульсный/асимметричный/резонансный/обратный заряд всегда лучше штатного CC/CV;
- что малый хвостовой ток, высокий SG, нормальный OCV, низкий R или высокий CCA доказывают полный SOC/C20/SOH;
- что высокий Iend/пузырьки/падение U сами по себе доказывают КЗ или переполюсовку;
- что успешное восстановление одной батареи доказывает безопасность/ресурс метода;
- что лабораторная 2V cell, flooded 40Ah, carbon-fibre PV или stationary AGM результат переносится на автомобильную Ca/Ca72Ah/EFB/AGM без отдельной валидации.

## 6. No-go: действия, которые не следуют из научной базы
1. Намеренно переразряжать элемент/батарею до инверсии, проводить обратный заряд или отрицательные импульсы ради «восстановления».
2. Использовать повышенное напряжение/газовый MIX как универсальную процедуру; особенно переносить flooded метод на AGM/GEL/VRLA.
3. Вскрывать VRLA, доливать воду/кислоту, менять электролит или смешивать рецептуры старой батареи без отдельного профессионального лабораторного процесса.
4. Пытаться «лечить КЗ» повышенным напряжением, импульсами или продолжением разряда.
5. Добавлять carbon/expander в готовую батарею или делать retrofit по материалам заводских NAM/PAM исследований.
6. Объявлять SOH/C20 по CCA, Rdc, DCA, OCV, Iend или одному ML/EIS score без независимого ground truth.
7. Считать один U12V достаточным для диагностики состояния каждой из шести ячеек.
8. Менять RD6018, ESP, node104, HA, силовые профили или БВ-600 на основании отчётов R01–R19 без отдельного решения D08 и полного dry-run.

## 7. Требования к будущей метрологии и данным
| Величина | Минимально нужные данные | Типичная ошибка, которую нужно исключить |
|---|---|---|
| U/I | Синхронные калиброванные U(t), I(t), знаки и точность/частота записи | Несинхронность, неверная полярность, потеря коротких переходов |
| T | Место датчика, контакт/ambient, T(t), thermal lag | Приравнивание ambient к температуре активной массы |
| SOC | Начальный якорь, T, rest, history, coulombic integration и uncertainty | OCV одной точки без предыстории |
| C20 | Стандартный ток, T, full-charge/rest protocol, cutoff, повторяемость | Ah из произвольного разряда называть C20 |
| CCA | Стандарт и T теста, прибор/метод, модель батареи | Считать CCA эквивалентом C20 |
| Rdc/EIS | Точная waveform, duration, frequency, SOC, T, contacts, calibration | Смешивать R0, pulse-R, 1kHz и EIS |
| SG | Только flooded serviceable; T correction, прибор, вертикальная координата z | Одна верхняя проба как средняя SG |
| Self-discharge | Изолированная внешняя нагрузка, фиксированные rest/T/SOC, повторные U и reference capacity | Падение U на подключённой нагрузке назвать Ishort |
| Recovery durability | Matched standard-charge control, C20/CCA/throughput/EFC/calendar, failures/dropouts | Только один immediate Ah или 40-cycle test |
| Gas/water/thermal | Масса/SG для flooded, неинвазивные VRLA indicators, ∆T, pressure/gas only in safe lab | Игнорировать водопотери/thermal runaway |

## 8. Синтез диагностической логики (требования, не код)
1. **Data gate:** проверить калибровку, наличие U/I/T, синхронизацию, тип/модель, знак тока, условия и историю. Если данные неполны или противоречивы — UNKNOWN.
2. **Safety gate:** при аномальной температуре, опасном напряжении, подозрении на short/reversal или повреждение прекратить силовое воздействие и не пытаться выяснить механизм опасным тестом.
3. **Separate outputs:** хранить независимо measured C20, estimated SOC, estimated SOH_C20, CCA/power status, charge acceptance/DCA, Rdc/EIS, quality/confidence and source. Не схлопывать их в один «здоровье %».
4. **Mechanism hypotheses:** стратификация, сульфатация, soft-short, dehydration, corrosion, reversal — только SUSPECTED/CONSISTENT/SUPPORTED в зависимости от независимых данных. Не повышать до CONFIRMED по одному индикатору.
5. **Charge-stage semantics:** MAIN stage complete ≠ SOC confirmed; MIX stage complete ≠ SG homogenized; treatment complete ≠ capacity restored; capacity restored ≠ service life restored.
6. **Model-specific limits:** charge profiles, temperature compensation and safety limits привязывать к точной модели/паспорту и области применения, а не к одной метке Ca/Ca/EFB/AGM.
7. **No automatic recovery action:** любой восстановительный/десульфатирующий/высоковольтный режим остаётся отдельной исследовательской гипотезой, не автоматическим ответом на диагностический статус.

## 9. Приоритеты незакрытых гипотез
Все H01–H61 остаются OPEN, кроме H09, который имеет ограниченный SUPPORTED status только в отдельных публикациях. Приоритет следующей научной проверки:
- P0 — H06/H19/H21/H26/H29/H53/H54/H57/H58: повторяемость C20, контроль штатного заряда, UNKNOWN/diagnostic risk, durable recovery.
- P1 — H01/H03/H04/H14/H15/H22/H23/H24/H27/H28: различимость механизмов и переносимость оценок на независимые батареи.
- P1 — H30/H32/H33/H34/H35/H38/H39/H40/H41/H42/H43–H48/H55/H56/H59: chemistry-specific material and temperature interactions, только matched designs.
- Никакая гипотеза не переводится в код/силовой режим до независимой валидации, uncertainty analysis и D08.

## 10. Итог R20 и остаточные пробелы
R20 формирует согласованный evidence map C01–C96, открытые H01–H61, evidence grades, no-go boundaries и метрологические требования. Это **документальная синтеза**, а не завершение всей НИР и не доказательство конкретного charge algorithm.
R20 = PARTIAL: синтез выполнен; R01–R19 сохраняют свои PARTIAL статусы, потому что ряд источников доступен только как abstract/preview, нет независимой лабораторной репликации и нет полного battery-held-out/long-duration dataset. Никаких физических опытов и изменений RD6018/БВ-600 не проводилось.

## 11. Дополнительный аудит R20-A01 — слабые места доказательств (28.11.2026)
Новые источники A01–A04 и анализ 24_R20_EVIDENCE_GAP_AUDIT.md дополняют выводы C92–C96 и H60–H61 без изменения решения R20=PARTIAL. A01 Cleland2000 n126 новых герметичных АКБ: плюс 17% immediate после опасного переразряда+заряда, но нет контролируемого долговременного восстановления и числа below65% противоречивы (abstract 47/126 как 36.5%, indexed Results 46/126). A02 Mankov2026 n2 новых AGM9Ah до 300 циклов: +4.5/+6.7% — preventive cycle charging с недостаточными независимыми группами, не repair старой АКБ. A03 Catherino2004 — критика легенды «80% списанных АКБ излечимы от сульфатации» не является собственной эпидемиологией отказов. A04 Frenander2026, npj Clean Energy: 54 cells — Li-ion/NMC/graphite, НИКОГДА не цитировать для Pb-acid. Приоритеты: а) референс C20/uncertainty; б) matched обычный заряд контроль; в) 30/90-day/EFC durability; г) стоп/UNKNOWN на неидентифицируемом механизме; д) проверить оригинальные PDF A01/A02/A03. Физических действий, зарядных уставок, внедрений нет.


## R20-A02 appendix — measurement and longitudinal causal guardrails
The R20 source base is extended by 25_R20_LONGITUDINAL_METROLOGY.md (C97–C101, H62–H64). In Shamim et al. (2022) four AGM carbon-lead modules were observed for 18–28 months, but their reference capacity was the mean of two C5 discharges to 11.1 V, not C20. Each duty regime had only one independent physical battery. Early capacity rebound in ordinary cycling does not establish a restorative procedure. After 400 PS cycles the authors changed charge termination, confounding RTE deterioration with protocol changes. ZVEI leaflet 34 specifies capacity-test comparability for stationary batteries, not the automotive C20 standard. An independent standard-charge-only comparator plus calibrated uncertainty and longitudinal capacity/CCA/EFC are essential; simple pre/post is not causal evidence. The 72Ah/2% example is synthetic uncertainty sensitivity, not a charger specification. R20 remains PARTIAL; no production recommendation.

Status update 2026-11-28: cumulative registers C01–C101 / H01–H64, latest R20-A02 report 25_R20_LONGITUDINAL_METROLOGY.md. Historical R20 synthesis baseline above (C01–C96/H01–H61) preserved as original scope; additive analytical conclusions and hypotheses do not imply treatment validation.

### R20-A03 extension: controlled comparisons
Cumulative registry C01–C106 / H01–H67. Cooper 2002 six matched AGM pairs, Lam 1995 laboratory PCL, and Fraunhofer ISE 2002 stationary field maintenance distinguish ordinary conditioning from specialized waveform effects and treatment-withdrawal persistence. See 26_R20_CONTROLLED_COMPARISONS.md. R20 remains PARTIAL.

### R20-A04 extension: reversible loss and limits
Cumulative registry C01–C112 / H01–H70. Bopp 2010 provides 10.5-year field endpoint with selected cells and monitoring gap plus 81-specimen GEL storage factorial; Sandia 1998 and Energies 2019 demonstrate different endpoints and limits of inference. See 27_R20_REVERSIBLE_LOSS_LIMITS.md. R20 PARTIAL; no validated charging algorithm.

### R20-A05 extension: PCL and diagnostic identifiability
Cumulative registry C01–C117 / H01–H72. PCL interface and bulk mechanisms can coexist; Kwiecien and Badeda rechecks clarify missing cross-mechanism validation. 2026 field cohort supports OCV insufficiency but has selection and replacement confounding. Synthetic circuit counterexample shows nonunique spatial resistance attribution. See 28_R20_PCL_IDENTIFIABILITY.md. R20 PARTIAL.

### R20-A06–A08: original EIS and grouped models
Cumulative registry C01–C129 / H01–H76. Reports 29_R20_RAW_EIS_AND_LABELS.md, 30_R20_ZHIT_AND_CAPACITY.md, 31_R20_MULTIFEATURE_BASELINES.md. Original 2104 spectra, four cells. zHit is preliminary; residual capacity not fully charged C20. Multiband ridge does not beat FCE ridge on 26 common cases. On 24 three-frequency cases metric dependence persists. All remain exploratory; R20 PARTIAL.

### R20-A09 rest and history
Cumulative registry C01–C132 / H01–H77. Report 32_R20_REST_HISTORY.md: 31 four-hour rest records; identical Urest with 11-fold Q difference. No rest-only incremental benefit on full set. Joint FCE+EIS+rest signal in selected 26 cases; selection-dependent and exploratory. R20 PARTIAL.

### R20-A10 coverage and external datasets
Cumulative registry C01–C135 / H01–H78. Report 33_R20_COVERAGE_EXTERNAL_DATA.md. Full 31-case fallback comparison, same four cells; macro MAE 1.39013→1.10533Ah, one cell worsens. BBOXX metadata 1027; OPzS six series cells, 110 CSV, 579448 rows. External prediction not yet validated. R20 PARTIAL.

### S1 / R20-A11 charge and stratification
Cumulative registry C01–C139 / H01–H79. Report 34_S1_CHARGE_STRATIFICATION_OPZS.md; OPzS candidate discharge blocks, voltage outlier and DCA/SG quantitative sources. New RESEARCH_ACCEPTANCE.md 40/88 criteria. R20 PARTIAL; no hardware approval.

## S1 block 2 — C140–C146 / H80–H81
Reports 35–36 add measured water-loss lot variability, charge history, local sulfate/current timing, geometry-dependent DCA and pore-flow restriction during gassing. No single tail current, gas onset, density or short DCA metric identifies charge completion or retained capacity. Distinguish bulk mixing from pore transport, and flooded from VRLA. C01–C146; H01–H81. Evidence grades and transfer limits in reports; independent target-model validation remains open.

## S1 block3
C01–C149 / H01–H82. Report37: industrial comparison and independent spatial measurement of starter battery; distinguish bulk homogenization, equalization across cells and functional recharge. R09-K documentary distinction accepted, specific treatment remains UNKNOWN and direct water/full protocol open. No physical validation.

## S1 block4 — completion matrix
C01–C153 / H01–H83. Report38: charge completion, full SOC, functional capacity, recovery and resource are independent claims; gas and construction transfer boundaries explicit. R04/R08/R10/R14 K bounded documentary PASS; target-model thresholds UNKNOWN, no P advanced. S1 deliverable assembled, residual gates carried forward; S2 recovery and resource next. No physical or production acceptance.

## S2 block1
C01–C157 / H01–H84. Report39: waveform gas normalization, historical capacity comparison, unequal returned charge and distinction of observed versus modeled life. R03-K bounded documentary accepted; specific efficacy UNKNOWN and R03-P open. No new physical evidence.

## S2 block2
C01–C161 / H01–H85. Report40: retained capacity can coexist with declining PSoC operability; full-charge/checkup itself is intervention; distinguish recovery yield denominator, observation and EOL. R19-K bounded documentary accepted; durable superiority over ordinary charge NOT_ESTABLISHED; no P or physical acceptance.

## S2 block3
C01–C164 / H01–H86. Report41: material-dependent HER sign, PAM/NAM coupled reaction and corrosion behavior, electrode-resolved discharge/reversal distinctions. R17-K/R18-K bounded documentary accepted; no optimal additive, reverse-charge efficacy or physical protocol accepted. No production actions.

## S2 exit / S3 admission
C01–C166 / H01–H87. Report42: synthetic signed waveform metrology and retention design, strict OPzS rest screen negative, BBOXX acquisition denied. S2 deliverable complete with open P criteria; S3 started. 52/88 unchanged. No new physical evidence or mechanism classification.

## S3 block1
C01–C171 / H01–H88. Report43: CT/SEM detection limitations, independent teardown mechanical/sediment shorts, Conradt source correction and synthetic nonidentifiability. R04-D-K/R13-K bounded documentary accepted, R04-D-Q/P and R13-P open. No chemical bridge or physical classifier acceptance.

## S3 block2
C01–C175 / H01–H89. Report44: published SOH plot-data arithmetic reproduced but not admitted as external validation; load history and method-specific capacity comparisons; IEC scope updated. R11-K documentary accepted; R11-P and R05/R06/R07/R12-K remain OPEN. No physical acceptance.

## S3 block3
C01–C179 / H01–H90. Report45: independent SciPy all-MAT decoder and author-mask reproduction PASS, intended mOhm scale established but calibration/timestamps absent. External literature capacity/resistance counterexample; R07-K bounded documentary accepted. R06-K external cohort/chronology and all associated P remain OPEN. No physical classifier or model accepted.

## S3 exit / S4 block1
C01–C183 / H01–H91. Report46: independent measured temperature-capacity curve, capacity anchor in SOC estimation, published ageing percentage inconsistencies and extended cold relaxation. S3 main deliverable complete; R05/R06/R12-K and R04-D-Q remain open, no physical acceptance. S4 started, R15-Q accepted, K/P open.
