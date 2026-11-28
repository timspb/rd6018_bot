# Консолидированные выводы v1.0
Это синтез текущих отчетов, не окончательно закрытая доказательная база. Для каждого положения сохранять границы и ссылку на отчет.
C01 — PbSO4 штатный продукт разряда; рекристаллизация и морфология влияют на зарядоприемность. R02, Takehara, Pavlov; не сводить все отказы к крупным кристаллам.
C02 — зарядоприемность зависит от SOC, температуры и предыстории. R01, Kowal et al.; универсальный диагностический порог не выведен.
C03 — стратификация изменяет локальную реакцию и импеданс; верхняя проба не равна средней плотности. R01, Variation of Impedance 2018; применимость зависит от конструкции.
C04 — универсальное преимущество импульсного заряда не установлено. R03, NASA TM-82709 и Mizumoto 2018; различать условия и контроль.
C05 — при фиксированном R и одинаковом среднем токе прямоугольные импульсы с нулевыми паузами дают омические потери выше DC в 1/D раз. R03, аналитический вывод; не полный тепловой баланс.
C06 — экстремальный переразряд повышает риск металлизации сепараторов при последующем заряде; не доказано, что конкретный начальный ток предотвращает КЗ. R04-D.
C07 — растворимость PbSO4 в кислоте немонотонна. R04-D, Craig/Vinal; не отождествлять растворенный Pb и свободный Pb2+.
C08 — НРЦ, CCA, ток CV и газовыделение не доказывают восстановление C20 или конкретный механизм дефекта. R01–R04-D/CASE-001; требуется независимая диагностика.
C09 — восстановление химического состава не гарантирует восстановления решеток, сепараторов и структуры активной массы. R02.

C10 — дозаряд, перемешивание и выравнивание имеют различные критерии; рост плотности не доказывает рост емкости. R04.
C11 — идеальный электролиз 1 Ah дает 0.336 г разложенной воды на элемент; реальный газовый ток неизвестен. R04, закон Фарадея.
C12 — заводские пределы привязаны к конструкции и модели; универсальная уставка MIX не выведена. R04.

C13 — напряжение после отключения тока не равно гарантированно равновесной ЭДС даже после нескольких часов; при низкой температуре релаксация может превышать 100 ч. R05-S01, границы по конструкции и условиям.
C14 — Rcharge60 является протокольно-зависимым показателем зарядной поляризации; его обратимый рост при PSoC наблюдался на Leoch в BESS. R05-S02; не чистое омическое R и не C20.
C15 — параметры многокомпонентной релаксации не уникально идентифицируют физический механизм; учитывать конечную длительность импульса и частоту измерений. R05.

C16 — частота, предыстория и режим измерения влияют на связь импеданса с емкостью. R06.
C17 — неоднородность сульфатации может сохраняться после перемешивания электролита. R06-S01.
C18 — конечновременное DC сопротивление включает поляризацию; не эквивалентно R0 или Z(1kHz). R06.

C19 — механизмы деградации могут сочетаться и причинно усиливать друг друга; устранение симптома не равно устранению причины. R07.
C20 — функциональная диагностика и установление механизма отказа требуют разных доказательств. R07.
C21 — при стратификации возможно снижение HF импеданса одновременно с ростом Rct. R07-S04.

C22 — малый конечный ток не доказывает полный заряд, в том числе при сульфатации. R08-S02.
C23 — инкрементальная кулоновская эффективность может резко снижаться при высоком SOC. R08-S01, один образец.
C24 — окончание MAIN и подтверждение полного SOC различны. R08.

C25 — ранняя дестратификация исследована на flooded, перенос на автомобильные EFB/CaCa открыт. R09-S01.
C26 — стабилизация плотности при выравнивании не доказывает отсутствие вертикального градиента. R09-S02–S04.
C27 — интеграл клеммного тока не равен газовому заряду. R04/R09.

C28 — убывающая отдача десульфатации наблюдалась в конкретном опыте Shi (R10-S01).
C29 — высокомощный разряд не C20; эффект формы тока не выделяется при неравных воздействиях (R10-S02).
C30 — восстановление емкости не устанавливает механизм без независимого контроля (R10).

C31 — определение C20 зависит от строго определенного тока, температуры и порога конечного U, не эквивалентно Ah при произвольном разряде. R11-S01.
C32 — закон Пейкерта эмпирический при постоянных I/T; простой перенос на переменный ток не даёт надежной оценки SOC. R11-S02–S04.
C33 — концентрация кислоты и температура существенно влияют на доступную ёмкость и параметры разряда, их необходимо фиксировать. R11-S04/S06.
C34 — CCA/внутреннее сопротивление/режим Repair не заменяют независимого контрольного C20. R11-S01 и TG-TRIAGE-001.

C35 — SOC_C и SOH_C совместно зависят от неизвестного Cmax; без независимой информации одна величина не определяет обе (R12).
C36 — ошибка SOC не тождественна ошибке SOH: Wang 2021, два AGM, табл.2–3 (R12-S01).
C37 — малый MAE на 17 следующих циклах одной сборки не доказывает перенос на другие батареи/условия (R12-S02).
C38 — CCA/одночистотный R и проводимость не заменяют независимый C20 и charge acceptance (R12-S07/TG-05).
C39 — EIS/импульсно-релаксационные методы многообещающи, но требуют независимой калибровки и соответствующего измерительного оборудования (R12-S03/S04).

C40 — частичный внутренний short способен вызвать существенную потерю заряда одного элемента в покое; не локализуется одним OCV всей батареи. R13-S01.
C41 — отсутствие роста сопротивления при полном SOC не исключало развивающийся soft short в лабораторном опыте Conradt; при более низком SOC динамика была заметнее. R13-S01.
C42 — высокий ток окончания заряда неспецифичен для КЗ: возможны газовыделение, примеси, потеря воды. R13-S01/S04.
C43 — 6% cell short как главная причина отказа в выбранной серии полевых б/у АКБ Conradt 2023 не является популяционной вероятностью либо вероятностью для CASE-001. R13-S02.
C44 — нормальный химический саморазряд, внешняя паразитная нагрузка, постзарядная релаксация и внутренний short имеют разные механизмы; дельта напряжения без контроля условий не доказывает Ishort. R13.

C45 — Ca/Ca=семейство сплавов решётки, AGM/GEL=иммобилизация электролита с VRLA, EFB=модифицированная flooded конструкция. Эти факторы пересекаются; маркировка не задаёт режим заряда. R14-S01–S03.
C46 — EFB сохраняет жидкий электролит, его DCA/стратификация/ресурс зависят от рецептур NAM, волоконных слоев, геометрии и кислоты; не единый «типовой» показатель. R14-S02/S04/S09.
C47 — VRLA AGM/GEL работают с кислородной рекомбинацией, при перенапряжении возможны клапанный сброс газов, необратимая потеря воды и перегрев; паспортные режимы обязательны. R14-S03/S07/S08.
C48 — В стареющих/крупных AGM возможны градиенты концентрации и насыщенности, поэтому абсолютное «стратификации не бывает» неверно. R14-S06 abstract-level; границы не определены.
C49 — DCA зависит от углерода NAM, объема кислоты, SOC и предыстории, и по одному обозначению EFB/AGM не определяется. R14-S04/S05/S13.
C50 — Pb-Ca/Pb-Ca-Sn обычно снижают расход воды/саморазряд относительно старого Pb-Sb в сравнимых конструкциях, но есть компромиссы по пассивации, коррозии и росту решетки. R14-S01/S10.
C51 — Сравнительные маркетинговые/промышленные утверждения EFB против AGM по DCA расходятся (VARTA vs Hitachi/Energywith), и не разрешаются без одинаковой методики, SOC/T и образцов. R14-S02/S09.

C52 — Доступная емкость при текущей T и необратимый SOH вследствие T-истории различны; холод снижает кинетическую доступность без обязательной необратимой потери. R15-S01/S06.
C53 — Температура ускоряет коррозию/водопотерю и в float уменьшает ресурс, но правило 2×/10°C лишь приближение для отдельного режима/механизма. R15-S03/S07.
C54 — Тепловой баланс включает энтропийные, поляризационные и термохимические эффекты, не равен только I²R. R15-S02.
C55 — Коэффициент компенсации U различается даже у float продуктов одного изготовителя: EnerSys SBS XC+ −3 mV/(cell·°C), EON −4; паспорт конкретного изделия обязателен. R15-S04/S05.
C56 — В VRLA перезаряд может вызвать положительную T↔I обратную связь; видимый газ не обязателен как предупреждение. R15-S08/S02.
C57 — Сравнение SOH и Ri без известной T-истории и предыстории заряда не научно воспроизводимо. R15-S01/S09.
C58 — Внутри элемента T неоднородна; наружный/ambient датчик не измеряет T активной массы напрямую. R15-S02.

C59 — Равновесная растворимость PbSO₄ в растворах H₂SO₄ нелинейна: при 25°C min около 0.3 мас.% и max около 10 мас.% кислоты, Table5 NBS 1939 S01 оригинал проверен.
C60 — ~42.5 мг/л PbSO₄ в чистой воде при 25°C подтверждено независимыми справочниками, не г/л; отношение к растворам 35/40/45 мас.% ≈21/28/35, а не универсальные 40. R16-S01/S09.
C61 — Физический максимум проводимости H₂SO₄ при ~31.1 мас.% и 25°C не равен оптимуму растворимости сульфата/ресурса АКБ. R16-S02/S01.
C62 — Начальная C20 максимум около SG1.30, но ресурс падает при высокой исходной SG в NAM-limited 12V/32Ah модельных ячейках Павлова, не универсально и не разрешение добавлять кислоту. R16-S03.
C63 — Acid-limited и NAM/PAM-limited конструкции имеют разную зависимость C, DCA, цикла от состава электролита; сравнение без конструкции некорректно. R16-S03/S04.
C64 — Для Pb–Ca–Sn качество решётки связано с микроструктурой, Sn₃Ca, Ca/Sn/Ag, изготовлением, пассивацией и адгезией активной массы; Ca/Ca не задаёт алгоритм заряда. R16-S05–S08.
C65 — Bulk SG, концентрация в порах пластин, растворимость PbSO₄ и риск дендритного КЗ причинно связаны, но не тождественны. R16-S01/S03/R04-D/R13.
C66 — Нельзя оптимизировать conductivity, solubility, C20, DCA и ресурс одной «идеальной плотностью» без многокритериального контроля. R16-S01/S02/S03/S05.

C67 — NAM carbon can improve HRPSoC via electrical contact, PbSO4 morphology and double-layer capacitance but relative mechanisms depend on composition/duty; R17-S02/S07/S09.
C68 — At fixed 2wt% carbon in model 2V/2.5Ah NAM-limited cells, increased Sext from 7.1→92.1 m2/g raised short-term CA 0.21→0.58 A/Ah, plateau near 159.3 m2/g; R17-S01 original.
C69 — DCA rankings from brief test lost quantitative resolution after long run-in/parking; cannot infer lifetime benefit from initial DCA; R17-S01 original.
C70 — Carbon-foam 1% yielded 3642 vs blank 1267 HRPSoC microcycles at 2C/50% SOC, with lower counts at 1.5%/2%; not full cycles or universal optimum; R17-S03 indexed.
C71 — NCC 4324 vs AC1834 vs blank809 HRPSoC microcycles in another study; not directly comparable to S03; R17-S06 indexed.
C72 — Additional carbon may accelerate hydrogen evolution, increase water loss/self-discharge and lower efficiency; VRLA oxygen cycle matters; R17-S02/S09.
C73 — Lignosulfonate/BaSO4/carbon expander mixture has separate effects, a 2006 study ranked synthetic lignin ahead of other modifiers for its cells; R17-S08 abstract.
C74 — PAM carbon is distinct from NAM; some 2025–26 AGM studies report benefits but generality and oxidative stability are unproven, do not override manufacturing controls; R17-S02/S10/S11/S12.
C75 — DCA transient charge acceptance ≠ C20, CCA, capacity retention, water loss or long-term resource; R17-S01/S04/S05/S13.

C76 — Electrode inversion, negative terminal Ucell and negative entire U12V are distinct events; observations of one do not establish simultaneous others. R18-S01/S02.
C77 — A weak cell in series can reverse under discharge while Utotal remains positive; total U alone does not certify every cell state. R18-S01/S03.
C78 — Negative-electrode inversion can oxidize organic lignosulfonate expanders and cause severe polarization heating; not automatically reversible even if U recovers. R18-S01.
C79 — pH disturbance during advanced discharge was observed on flooded Planté and SLI cells, but no general safe early cutoff threshold for AGM/EFB validated. R18-S02.
C80 — Two carbon-fibre PV 12V batteries survived accidental terminal polarity inversion with apparent short-term C10 restoration (2004), but long-term life not established (only one accelerated PV cycle at publication). R18-S05.
C81 — Karami 2009 observed five flooded 40Ah batteries improve mean measured Ah from 7.2 to 35.0Ah after multi-stage inverse/chemical prep, but effect of inverse charge not separated from acid replacement/standard recharge, and safe long-term resource not validated. R18-S06.
C82 — Karami 2009 text 'all <25%' before vs Table1 13/40=32.5%, 10/40=25% is an internal report inconsistency. R18-S06.
C83 — Short reverse pulses superimposed on normal charging are not whole-cell reverse charging or polarity inversion; different evidence required, R18-S09/R03.

C84 — Karami et al. (2009) report 40 charge-discharge cycles and ≥80% cycle endurance relative to a fresh similar battery; metric, n and EOL are not defined in the accessible section. R19-S01.
C85 — Lee et al. (2023) report a 40-cycle recovered 2V-cell test: average discharge 91.3% nominal / 98.6% of new, cycle 40 at 89% nominal; SEM after testing shows lower porosity and sulfate accumulation. R19-S02.
C86 — Ohajianya et al. (2021) report a 10-week time series: at 10 weeks B1/B2 remain +59.1/+14.1% vs baseline, B3/B4 are −20.1/−27.7%; no control and PV charging co-intervention, so causal effect of desulfator unresolved. R19-S03.
C87 — Shi et al. (2012) show +41% capacity in one desulfated VRLA cell after 313h, but final 56.3Ah vs 88Ah nominal and no post-recovery life test; companion 2013 study describes three other cells as dehydrated. R19-S04.
C88 — PNNL 2022 demonstrates a stronger durability measurement pattern: four AGM modules, 18–28 months, 289–728 EFC, monthly capacity and bimonthly pulse-resistance reference tests; this is an aging benchmark, not proof of a restoration method. R19-S09.
C89 — No accessible controlled multi-month/multi-year inverse-charge recovery trial on modern automotive Ca/Ca/EFB/AGM with matched standard-charge controls and independent C20/CCA/EOL follow-up was found in the R19 review.
C90 — IEC 60095-1:2018 corrected 2026-02 provides the applicable 12V starter-battery test framework including 20h capacity, reserve capacity, cranking, charge acceptance, retention and endurance; optional cycle endurance test covers passenger-car batteries up to 100Ah. R19-S10.
C91 — R18-S06 Karami 2009 дополнительно сообщает 40 циклов сравнительного теста и авторское утверждение ≥80% cycle endurance относительно свежей батареи; точная метрика, n и EOL не определены, поэтому это короткий screening, а не доказательство multi-year service life. R19-S01.

C92 — Cleland et al. 2000, 126 new stored sealed batteries: publisher abstract states mean +17% immediately after a multi-stage intervention including deep over-discharge, but effect of that step, matched baseline, long-term retention and safety are not established. R20-A01/A01, E3/T3.
C93 — Cleland abstract 47/126=37.30% cannot equal published 36.5%, indexed Results has 46/126=36.51%; exact count disputed until original Table2 is inspected. R20-A01/A01.
C94 — Mankov et al. 2026 two NEW 9Ah AGM up to 300 cycles and claimed 7.8Ah / +4.5% / +6.7% are a small-sample charge-strategy prevention study, not demonstrated recovery of aged batteries. R20-A01/A02 E3/T3.
C95 — Frenander et al. 2026 tests pulses on 54 lithium-ion NMC/graphite cells, not lead-acid; no quoted lifetime benefit may be transferred as evidence to this NIR. R20-A01/A04 excluded.
C96 — Catherino et al. 2004 question the popular 80%-curable sulfation claim; critique is not an empirical prevalence measurement and PbSO4 alone is not a specific failure diagnosis. R20-A01/A03 E3.

C97 — ZVEI (2020) separates capacity tests from impedance/OCV indicators and emphasizes matched preparation/temperature/cutoff, but the leaflet concerns stationary batteries; it does not replace automotive IEC 60095-1. R20-A02/B01.
C98 — Shamim/PNNL (2022) measured four AGM lead-carbon modules longitudinally for 18–28 months, one per duty regime; reference capacity was average of TWO C5 tests to 11.1 V, not automotive C20. No between-module replication within regimes. R20-A02/B02.
C99 — In PNNL-2022 PS modules, apparent capacity recovered after an initial loss without a specific restoration treatment; possible mechanisms remain uncertain. A protocol change after 400 PS cycles contributed to measured RTE changes; raw KPI drift is not necessarily intrinsic aging. R20-A02/B02.
C100 — Pre/post capacity change by itself does not isolate unique treatment effect from charging, conditioning, calendar drift, measurement change or selection bias; paired matched standard-charge-only controls, protocol invariance and longitudinal endpoints are required for causal claims. Mathematical methodological conclusion R20-A02.
C101 — Hypothetical independent standard sigma=2% of Cnom72Ah per capacity measurement gives normal-approx 95% change halfwidth 3.99Ah and one-per-arm DID halfwidth 5.64Ah; analytic sensitivity, NOT measured instrument precision or charger validation. R20-A02, tools/r20_capacity_evidence_math.py.

C102 — Cooper 2002 six matched AGM pairs show heterogeneous high-rate discharge-time changes: pulse wins 2, ordinary wins 3, tie 1; four ordinary batteries improved. Not C20; control rectifier itself ripple-bearing; no population estimate. R20-A03/S01.
C103 — Relative ratios of small improvement percentages may exaggerate practical effects; Cooper pair D 2.60% versus 6.26% is +3.66 percentage points, not 140% capacity recovery. R20-A03/S01.
C104 — Lam 1995 2V laboratory Pb-Ca-Sn G2 cells under selected charge regimes reached 22 ordinary cycles versus 8, 77 and 79 pulse cycles; waveform and average current differ between ordinary and pulse. No universal pulse superiority. R20-A03/S02.
C105 — Lam 1995 Fig.5 shows near recovery at early induced PCL followed by renewed decline after treatment withdrawal; later intervention stabilized rather than restored capacity. Not persistent recovery of intact aged batteries. R20-A03/S02.
C106 — Fraunhofer ISE 2002 reports nominal capacity recovery in one long-stored OPzV and a distinct four-year field maintenance observation; do not equate the two cohorts or extrapolate stationary protocols to automotive batteries. R20-A03/S03.

C107 — Wagner/Sauer 2001 and Bopp 2010 same Talhof cohort: seasonal differences up to 20% between C10 tests after different charge preparation. End-of-charge voltage alone not proof of full charge. R20-A04.
C108 — Bopp 2010 selected cells 2001–2008: high capacity in cells 13/14 coexists with dendrite-marked cells 6/24, one zero capacity. Monitoring gap and no parallel long-term control. R20-A04.
C109 — Bopp 2010: 81 GEL 6V/1.2Ah batteries, 3×3×3 conditions with three specimens each; prolonged hot storage limits subsequent C5 recoverability. Not automotive C20. R20-A04.
C110 — Bopp Fig.6 approximate 0.22→0.56Ah gain still below half nominal; near-zero gain with near-zero capacity is not recovery success. Water loss association not unique diagnostic. R20-A04.
C111 — Hund 1998 flooded golf-cart case: about 600Ah input, final 151Ah/~80% initial even with restored SG. No incremental capacity series or optimal stopping proof. R20-A04.
C112 — Energies 2019 field bank: improvement of working capacity and SG over three months but no standardized final capacity test; multiple controller changes, Ah accumulator drift and tail current do not establish full SOC. R20-A04.

C113 — Positive grid/PAM interface sulfate and bulk NAM sulfate are not equivalent diagnoses; contact loss/corrosion may promote secondary sulfate. PCL mechanism sources abstract-only. R20-A05.
C114 — Kwiecien 2018 sulfate-related EIS correlation in four model cells cannot validate corrosion discrimination, left for future work. ICP-OES sulfur does not uniquely measure pure solid PbSO4. R06 recheck; R20-A05.
C115 — Badeda 2018 48 float VRLA without periodic capacity tests or final post-mortem cannot validate capacity mapping or specific chemical labels. R06 recheck; R20-A05.
C116 — Selected failed 2026 VRLA had OCV 13.2–13.3V with 10–30% capacity; replacements and temperature order prevent paired temperature inference. Indexed publisher text only. R20-A05.
C117 — Synthetic linear circuit yields exactly identical terminal spectra and steps for different grid/interface series resistance partitions. Chemical classification requires independent constraints; not a claim that all EIS is useless. R20-A05.

C118 — Kwiecien 2018 original supplement: 2104 spectra represent four physical model cells and 35 checkups, not independent batteries. R20-A06.
C119 — Unfiltered soft-cell impedance ratios at nominal 80% SOC after 90 FCE differ between cells and frequencies; validity and unit reconciliation remain necessary. R20-A06.
C120 — Raw hard-cell after-charge/after-cycling impedance changes differ by cell and frequency; actual SOC not matched. R20-A06.
C121 — Kwiecien 2019 dissertation: severe residual capacity loss can coexist with relatively low local NAM sulfate-associated sulfur and greater PAM impedance change; shedding suspected, not confirmed. R20-A06.
C122 — Dissertation corrosion endpoints incomplete; no validated corrosion discriminator. R20-A06.
C123 — Dissertation TC181-2 explicit 3.7→7.6Ah endpoints conflict with later wording; visual verification pending, no durable recovery proof. R20-A06.
C124 — Native-unit zHit acceptance differs by bias and frequency; improved acceptance does not establish repeatability. R20-A07.
C125 — Filtered ~1kHz after-charge/after-cycling direction differs between hard cells; actual SOC not controlled. R20-A07.
C126 — Logged -2A residual discharge integration approximately reproduces published endpoints; residual after-cycling capacity is not fully charged C20. R20-A07.
C127 — In 26 common cases from four physical cells, leave-one-cell-out FCE OLS beats single-frequency impedance in most or all folds. No external validation. R20-A07.
C128 — On the same 26 observations, FCE ridge macro MAE 0.7994Ah is lower than both fixed multiband models with FCE; pooled MAE also lower. No universal EIS inference. R20-A08.
C129 — Three-frequency subset (24 rows) shows metric-dependent results; adding 0.1Hz has no robust incremental advantage. Report equal-cell and pooled errors on common cases. R20-A08.

C130 — Same four-hour quasi-rest voltage 2.165V at 15/135 FCE in one model cell with 10.403/0.922Ah residual capacity. Not fully charged C20. R20-A09.
C131 — On 31 residual-capacity records, tested rest, relaxation, temperature and prior-file throughput models do not beat FCE ridge; narrow/confounded conditions. R20-A09.
C132 — On 26 selected common cases, fixed FCE+two-band+rest model improves macro and pooled MAE but loses one held-out cell; exploratory selection-dependent signal, no external validation. R20-A09.

C133 — Frozen joint+fallback model on all 31 cases reduces macro MAE 1.39013→1.10533Ah, loses one of four cells; severe-degradation fallback error exceeds 4Ah. No independent validation. R20-A10.
C134 — BBOXX metadata 1027 selected VRLA, 491 repair and 536 censored outcomes; not population incidence, C20 or chemical labels. Raw sign convention differs from paper. R20-A10.
C135 — OPzS 110 CSV/579448 rows, six series cells in one bank. Released data lack density, overlapping/conflicting timestamps and temperature header mismatch require source-aware alignment. R20-A10.

C136 — Five aligned OPzS nominal-rate blocks end with cell2 lowest loaded voltage; capacity endpoint and mechanism not verified. R20-A11/S1.
C137 — Four physically implausible cell3 voltage records agree across mV/V columns; redundant-format equality does not establish physical accuracy. R20-A11/S1.
C138 — Kwiecien 2018 Table2: imposed density gradients decrease during measurement but remain nonzero until mixing; uniform SG does not prove restoration of active mass. R20-A11/S1.
C139 — Budde-Meiwes 2012: DCA conditioning/test method yields 3–8-fold differences; initial DCA and normalized current not universal completion criteria. Full machine text, visual figures unverified. R20-A11/S1.

C140 — Flooded nine-lot study normalized water loss varies 3.85-fold, associated with Te on both electrodes; no causal isolation. S1 report 35.
C141 — AGM oxygen recombination at high negative polarization inferred in one modified cell system; pressure not direct gas composition. S1 report 35.
C142 — ISS flooded PSoC gas onset reported before full charge; abstract only, exact rates unverified. S1 report 35.
C143 — Positive electrode EC-AFM current onset precedes visible sulfate dissolution; 30s little change, ~2min disappearance in model experiment. No whole-plate inference. S1 report 35.
C144 — Cyclon AGM charge duration and capacity vary with PSoC history; one cell per regime, conditioning confounding; no full-SOC or lifetime proof. S1 report 35.
C145 — DCA geometry and electrolyte reserve matter; EFB battery and reduced-cell rank reversal in Table A1, not universal transfer. S1 report 36.
C146 — Forced-flow negative electrode normalized flow fell 70% at gassing in one study and recovered in later rest; no universal pause or gas criterion. S1 report 36.

C147 — Industrial flooded mixing comparison at matched CF106% reduces gradient; waveform/order confounded, water figure not verified direct measurement. S1 report37.
C148 — One 60Ah starter battery had mean vertical density difference .079g/cm3 after three cycles and four-hour rest; upper sensor independently checked, lower not. S1 report37.
C149 — Multi-height optical sensing shows different density dynamics by height; one upper reading cannot establish complete homogenization. S1 report37.

C150 — Yuasa NP manual explicitly warns that current sensing can falsely indicate full charge early in charging an overdischarged battery; model-specific. S1 report38.
C151 — CYCLON manual distinguishes available capacity and periodic recharge sufficient for life; charge-return guidance differs from 2024 research, exact revision/application not equated. S1 report38.
C152 — Yu 2018 voltage-model validation excludes CV; efficiency fit inadequate above 98% SOC; cross-cell current comparisons confounded. S1 report38.
C153 — Integral recharge efficiency and differential storage efficiency are not interchangeable; midpoint assignment approximate. S1 report38.

C154 — James 2006 Table1 historical FAT-to-final capacities mixed, mean +2.1pp; no contemporary control or durability evidence. S2 report39.
C155 — James Table3 smaller total gas does not prove less gas per returned Ah; approximate normalization reverses hydrogen direction, actual Ah and matched final SOC unverified. S2 report39.
C156 — Minami equal average current does not ensure equal net charge with variable duration at voltage cutoff; discharge-duration improvement is not cycle-life proof. S2 report39.
C157 — Observed 150 cycles and extrapolated 1296 cycles in e-rickshaw study are distinct endpoints; abstract only, no measured 1296-cycle life. S2 report39.

C158 — Sandia 2009 carbon-enhanced VRLA bank retains reference capacity while PSoC intervals before recharge shorten; temperature/duty confounding and no EOL. S2 report40.
C159 — Same bank shows different capacities after rest and repeated cycling, even after approximate author temperature correction; preparation matters. S2 report40.
C160 — INL simulated hybrid drive-profile repetition counts recover after full recharge/capacity check in three SOC windows, not established persistent recovery. S2 report40.
C161 — Alipour/Nasseri 2025 screen 697 warehouse VRLA; claimed 72% recovery efficiency denominator and durability unverified in accessible material. S2 report40.

C162 — Hu 2016 observed material-dependent opposite HER effects and different capacity/water trajectories; positive grid corrosion at comparison failure; no universal additive benefit. S2 report41.
C163 — Cattelan 2026 three prototype batches show >5% normalized specific C20 improvement for selected PAM materials and different post-test structure; gas-current partition model-based, no measured EOL. S2 report41.
C164 — Ruetschi 2003 half-cell observations distinguish positive/negative limiting electrodes and complex reversal; terminal voltage cannot uniquely identify electrode state. S2 report41.

C165 — Signed Ah and Wh require separate sign-aware integration; zero net Ah can coexist with nonzero net Wh; sparse synchronous sampling may alias mean-square I. Synthetic verification only. Report42.
C166 — Strict six-channel OPzS same-test screening admitted no continuous hour-long rest at .1 or 1A; max 15/46min, no defect or relaxation inference. Report42.
