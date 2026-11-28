# Реестр гипотез
| ID | Гипотеза | Статус | Проверка/источник |
|---|---|---|---|
| H01 | Различение стратификации и сульфатации по переходным процессам | OPEN | R01, R05–R07 |
| H02 | Эффект формы тока при равном среднем токе/заряде | OPEN | R03, контрольные группы |
| H03 | Релаксация содержит диагностическую информацию о деградации | OPEN | R05–R07, не специфична сама по себе |
| H04 | Мягкое КЗ и разбаланс можно распознавать по совокупности признаков | OPEN | R04-D, R13 |
| H05 | Высоковольтный дозаряд дает полезный эффект при приемлемом ресурсе | OPEN | R04/R09, отдельно по конструкции |
| H06 | Восстановленная емкость сохраняется после циклов/хранения | OPEN | R19 |
| H07 | DCA коррелирует с остаточной емкостью | OPEN | R01/R12 |
| H08 | Начальный малый ток после экстремального переразряда увеличивает риск металлизации | OPEN | R04-D, прямое сравнение не найдено |
| H09 | При равном SOC предыстория влияет на зарядоприемность | SUPPORTED в отдельных работах | R01/R02; собственная проверка открыта |
| H10 | Перемешивание может имитировать восстановление сульфатации | OPEN | R01/R02/R04 |
| H11 | Интеграл MIX и динамика SG позволяют оценить достаточность воздействия при контроле потери воды | OPEN | R04/R09 |

| H12 | Rcharge60 характеризует обратимую деградацию зарядоприемности EFB/CaCa | OPEN | R05-S02, перенос из BESS требует испытаний |
| H13 | Многовременные признаки релаксации диагностически лучше одного dU/dt | OPEN | R05–R07, независимый C20 и контроль SOC/T |

| H14 | Набор стандартизированных DC откликов улучшает прогноз C20 относительно одного показателя | OPEN | R06/R12, независимая проверка |

| H15 | Совокупность независимых признаков повышает различимость механизмов отказа | OPEN | R07, независимая разметка и валидация |

| H16 | Комбинация tail current, стабилизации, Q, T и релаксации уменьшает ложные окончания MAIN | OPEN | R08, независимая емкость |

| H17 | Ранний MIX сокращает время при эквивалентных SOC, G и ресурсе | OPEN | R09-S01, перенос не проверен |
| H18 | U/I/T/релаксация позволяют прогнозировать вертикальный градиент | OPEN | R09, независимая калибровка |

| H19 | Последовательная оценка прироста C с неопределенностью сокращает бесполезные воздействия | OPEN | R10/R11/R19 |

| H20 | Периодическое воздействие 0,05C 5–7 минут каждый час может сохранять целевой результат при меньшем повреждающем воздействии, чем непрерывный форсированный заряд | OPEN, anecdote | TG-01; контроль равных Ah/Wh, SG(z), T и C20 |
| H21 | Конкретный режим Repair не дает преимуществ перед штатным зарядом при сопоставимых условиях | OPEN, anecdote | TG-02; независимый контролируемый A/B |

| H22 | k Пейкерта и температурная модель воспроизводимы для одного типа АКБ при 3+ стандартизованных скоростях | OPEN | R11; лаборатория |
| H23 | Стандартизованная U/I/T телеметрия и точное определение cutoff снижают разброс оценки C20 | OPEN | R11; метрология |

| H24 | OCV/rest/T/Rdc(t)/история заряда совместно уменьшают независимую ошибку SOH_C20 относительно простых baseline | OPEN | R12; leave-one-battery-out, C20 labels |
| H25 | SOC без актуального Cmax систематически смещен при низком SOH | OPEN | R12; сопоставить с независимым C20 |
| H26 | статус «недостаточно данных» уменьшит риск ошибочной диагностики без чрезмерного отказа от оценок | OPEN | R12; coverage/risk |

| H27 | U(t)+T(t)+Ri(SOC)+история зарядов лучше одного OCV/Ri для диагностики внутренней утечки при независимых labels | OPEN | R13-S01, лабораторный контроль |
| H28 | SOC и время покоя существенно меняют чувствительность Rdc к одному слабому элементу | OPEN | R13-S01, синтетическая проверка и эталонные реальные АКБ |
| H29 | отдельный статус недостатка данных снижает ложные диагнозы vs порога dU/dt | OPEN | R13, blind holdout |

| H30 | NAM carbon additives повышают DCA EFB при прочих равных, без автоматического выигрыша в ресурсе/водопотерях | OPEN | R14-S04/S05, matched independent DCA/C20/cycling |
| H31 | Концентрационная или насыщенная стратификация возможна у крупных/стареющих AGM | OPEN | R14-S06, специализированная лабораторная проверка без вскрытия VRLA в эксплуатации |
| H32 | При одинаковом EN50342-6 и SOC/T/истории порядок DCA EFB и AGM может зависеть от конструкции и производителя | OPEN | R14-S02/S09, independent paired test |
| H33 | Одна метка Ca/Ca не определяет безопасный/оптимальный зарядный профиль | OPEN | R14-S01/S10, cross-datasheet evidence audit |

| H34 | Часть потери емкости на холоде исчезает при повторном эталонном C20(25°C), без скрытой смены SOH | OPEN | R15; paired control + retest + safe specimens |
| H35 | Thermal dose в сочетании с U/SOC history лучше средней T предсказывает потерю ресурса | OPEN | R15; long-term multi-batch |
| H36 | Несколько внешних T-датчиков лучше одного ambient в обнаружении аномального локального нагрева | OPEN | R15/R13; safe validation |
| H37 | I²R-модель не объясняет переходный нагрев CC→CV без поляризации и термохимических членов | OPEN | R15-S02; calorimetry |

| H38 | Учет SG(z,t) и T улучшает объяснение Uocv и DCA flooded vs одной средней SG | OPEN | R16; native hydrometer and matched C20 |
| H39 | Более высокая исходная SG при сравнимых конструкциях повышает initial C20 до максимума, но ускоряет износ при равном throughput | OPEN | R16-S03; independent factorial cells |
| H40 | Градиент кислоты меняет локальную зарядоприемность сильнее, чем равномерный bulk SG при той же средней | OPEN | R16; lab reference electrodes |
| H41 | Pb-Ca-Sn alloy + process metallurgy predicts grid contact/corrosion better than Ca/Ca label | OPEN | R16-S05; factory specs and microstructure |
| H42 | Equilibrium PbSO4 solubility ratios alone poorly predict dendrite formation without migration/reduction/separator structure | OPEN | R16/R04-D/R13; literature + morphology evidence |

| H43 | Sext predicts short-term NAM DCA only until saturation from mixing/transport/positive plate limits | OPEN | R17-S01; independent replicated material batch |
| H44 | Carbon dose has nonmonotonic optimum in HRPSoC due to pore transport, HER and structural interactions | OPEN | R17-S03/S06; factorial trials with gas/Wh |
| H45 | Carbon+lignosulfonate+BaSO4 interactions explain cycle response more than carbon identity alone | OPEN | R17-S08; randomized controlled formulation |
| H46 | Early DCA tests overpredict preservation of rankings after months and prolonged rest | OPEN | R17-S01; prospective manufacturer held-out run-in |
| H47 | PAM carbon effects and oxidative stability/water-loss are different from NAM carbon | OPEN | R17-S10/S12; independent AGM lab C20/waterloss |
| H48 | Factory carbon-additive results cannot support any safe retrofit or high-voltage 'carbon treatment' of an existing battery | OPEN, negative safety assumption | R17-S01/S02 and absence of retrofit controls |

| H49 | Whole-pack voltage hides weak-cell inversion more often than per-cell U under known heterogeneous SOC/Cmax | OPEN | R18; offline 6-cell synthetic and labeled archival datasets |
| H50 | pH disturbance has insufficient early warning relative to safe cutoff across mixed AGM/EFB/T without precise sensor/chemistry | OPEN | R18-S02; retrospective data, no deliberate reversal |
| H51 | Reported Ah recovery in Karami can partly arise from acid/recharge/selection independently of reverse charge | OPEN | R18-S06; matched independent controls |
| H52 | Carbon-fibre plate structure increases resilience to accidental reversal for that specific construction, not all carbon additives | OPEN | R18-S05; long-life field followup |
| H53 | Quality/UNKNOWN diagnostics with independent cell evidence reduces unsupported confident short/reversal diagnosis | OPEN | R18-R13; safe synthetic holdout |

| H54 | Immediate Ah gain overstates durable benefit if water loss, gassing, active-mass shedding and porosity are not monitored | OPEN | R19; matched longitudinal datasets |
| H55 | Recovery response is non-monotonic and depends on baseline defect and charging environment | OPEN | R19-S03; controlled replication needed |
| H56 | Calendar time and storage SOC/T explain degradation variance beyond cycle count alone | OPEN | R19-S09 benchmark; restored matched samples |
| H57 | C20+CCA+pulse R+self-discharge+gas/water+∆T predicts usable recovery better than one Ah value | OPEN | R19; multivariate longitudinal data |
| H58 | 40-cycle screening does not reliably rank multi-year life | OPEN | R19-S01/S02 vs 18–24 month/EOL outcomes |
| H59 | Recovery percentages cannot be pooled across Gel/AGM/GFM/Ca-Ca/EFB without chemistry-matched controls | OPEN | R19-S02/S03/S06/S07/S08 |

| H60 | Part of the apparent capacity gain in stored NEW SLA batteries after destructive treatments could also arise from matched ordinary recharging and conditioning | OPEN | R20-A01/A01; only independent existing matched controls, no zero-voltage experiment |
| H61 | Claimed 4.5/6.7% pulse benefits in two fresh AGM batteries are sensitive to allocation/manufacturing variance and may not replicate across independent cells | OPEN | R20-A01/A02; publisher full methods and independent multi-battery experiment |

| H62 | Apparent early capacity rebound in AGM can be partly produced by ordinary conditioning, wetting and charging rather than unique restorative chemistry | OPEN | R20-A02/B02; matched independent control series and microstructure |
| H63 | Unversioned changes in charging termination, reference cutoff, and rest can mimic treatment/aging effects in resource KPIs | OPEN | R20-A02/B02 §4.6; blinded protocol audit and longitudinal replication |
| H64 | Measurement correlation and systematic temperature/instrument drift dominate uncertainty over technical repeats in some before/after comparisons | OPEN | R20-A02; calibration, inter-day reference repeats and hierarchical uncertainty modeling |

| H65 | Early reversible PCL responds differently than late structural/interface degradation; compare restoration versus stabilization | OPEN | R20-A03/S02; matched independent endpoints |
| H66 | At matched net charge, time, mean current and temperature, waveform-specific effects depend on grid/cure/defect and waveform | OPEN | R20-A03/S01/S02; replicate cells |
| H67 | Ordinary full-charge conditioning explains part of apparent recovery in some aged intact batteries | OPEN | R20-A03/S01/S03; C20/CCA and post-withdrawal storage/EFC controls |

| H68 | Reference minus working-preparation capacity tracks reversible operational undercharge independently of some aging modes | OPEN | R20-A04; matched fixed endpoint tests |
| H69 | Incremental reference-capacity gain and its uncertainty plus independent safety/functional metrics identify diminishing returns better than tail current alone | OPEN | R20-A04; archival validation |
| H70 | Water loss and internal shorts dominate residual capacity deficit despite improved charge completeness in some cases | OPEN | R20-A04; independent diagnostic evidence |

| H71 | Combined terminal features can discriminate dominant aging modes in fixed construction with independent labels; overlapping cases remain UNKNOWN | OPEN | R20-A05; held-out battery validation |
| H72 | Discharge discontinuity and invalid EIS predict weak-cell/failure risk independently of OCV | OPEN | R20-A05; distinguish instrumentation artifacts, validate independently |

| H73 | Multiband and preparation-state features may add information beyond single-frequency screening | OPEN | R20-A06; no independent cohort |
| H74 | Spatial sulfate distribution and active mass integrity may explain similar sulfur assays with different spectra | OPEN | R20-A06; independent chemical and imaging evidence |
| H75 | Multiple EIS frequencies and preparation/history can improve grouped residual capacity prediction over cycle baseline | OPEN | R20-A07/A08; tested variants negative on primary common set |
| H76 | Independent pre-discharge resting voltage and history features improve residual capacity prediction over FCE | OPEN | R20-A08; verify timestamps and independent cells |

| H77 | Complementarity of rest relaxation and multiband EIS may improve cross-cell prediction with known cycle history | OPEN | R20-A09; predefine model, coverage-aware baseline, independent cohort |

| H78 | Invalid measurements or missingness may signal severe degradation | OPEN | R20-A10; distinguish protocol/instrument confounders; independent prospective coverage and abstention |

| H79 | Repeated lower loaded cell voltage under matched state/rate/T may identify series-cell outliers | OPEN | S1/A11; verify measurement channels and independent discharge reference |

| H80 | Independent reaction/gradient indicators and reference capacity may reduce false MAIN/MIX completion | OPEN | S1 report 35; matched tests, separate chemical and functional targets |
| H81 | Bulk SG and pore transport measurements may distinguish mixing from improved acceptance | OPEN | S1 report 36; matched SOC/T/history, independent Q |

| H82 | Validated spatial gradient plus independent water and retained-capacity endpoints may distinguish useful mixing from unnecessary extra charge | OPEN | S1 report37; matched flooded specimens, model-specific controls |

| H83 | Independent functional reference, valid actual CV telemetry and model-specific history may reduce false charge completion relative to tail current | OPEN | S1 report38; matched independent specimens |

| H84 | Matched final functional charge/history and measured Q/Wh/gas may distinguish waveform benefit from unequal charge and ordinary conditioning | OPEN | S2 report39; independent controls |

| H85 | Matched multi-endpoint longitudinal tests may detect functional charge-acceptance decline despite unchanged reference capacity | OPEN | S2 report40; independent controls, fixed preparation |

| H86 | Joint NAM/PAM structure, gas/water and capacity endpoints may distinguish interface/transport improvements from apparent current gains | OPEN | S2 report41; independent matched factory specimens |

| H87 | Independent waveform bandwidth/energy calibration and matched functional charge may reduce waveform comparison bias | OPEN | Report42; actual measurement system not validated |

| H88 | Independent retained-capacity and per-cell voltage with physically verified contact/phase labels may distinguish loss mechanisms | OPEN | S3 report43; independent validation and coverage |

| H89 | Independent specimen IDs, prelabel traces and measured reference capacity may prevent misleading accuracy from duplicate plot outputs or derived labels | OPEN | S3 report44; independent validation |

| H90 | Independent labeled specimens with synchronized measurements, known scale and matched reference preparation may reduce bias of phase-only archive joins | OPEN | Report45; external validation pending |

| H91 | Matched specimen return-to-reference temperature, fixed reference discharge, measured thermal lag and matched throughput may separate reversible availability from ageing | OPEN | Report46; independent validation pending |
