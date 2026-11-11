# BW600 + XH-CDC-MK — исследование схемы и протокола (2026-11-09)

**Тип:** исследование только по открытым источникам. Никакой доступ к node104, реальному BW600, RD6018, ESP/HA или силовым цепям не осуществлялся. **Production/installation запрещены в текущей работе.** Источники имеют разную доказательную силу: ATORCH manual — документ изготовителя, Kirich — измерения третьей стороны, PeeJay — обратная разработка конкретной прошивки; совместимость с нашей аппаратной ревизией не подтверждена.

## 1. Подтверждено

- BW600 — электронная нагрузка 150/300/450/600 Вт (с расширением — больше), режимы CC/CV/CR/CP и тесты CDC (charge/discharge/charge), CDCDC, CDxn (1–99 групп). Важно: CV-load нельзя применять непосредственно к АКБ, руководство запрещает.
- XH-CDC-MK — НЕ зарядное устройство и НЕ регулятор тока. Коммутирует внешний источник (RD6018) к АКБ для зарядных стадий, BW600 исполняет разряд; номинально 100 В / 20 А. Источник устанавливает ток и напряжение.
- Заряд завершается по установленному верхнему напряжению либо низкому току; паузы между этапами есть. Полный цикл CDC с подключением/отключением лабораторного источника проверен в обзоре Kirich.
- BW600 имеет отдельный вход внешнего NTC и цифровую индикацию ETS, CPU/MOS температур; **не установлено**, сохраняет ли ETS телеметрию на USB при выключенной нагрузке или при разомкнутой цепи зарядника.
- BW600 USB HID подтверждён только для конкретного **BW-600W-DK V2.0.5**: VID/PID 0483:5750, 64-байтные HID report, OUT 0x55 / IN 0xAA. Это **не** старый FF55 UART-протокол ATORCH.
- Исходники PeeJay/Atorch_BW600 расшифровывают 0x47 CC, 0x48 CV, 0x49 CR, 0x4A CP; 0x21 setpoint float32 big-endian; 0x25 load on/off; 0x05 telemetry и 0x03 активная уставка. Телеметрия U/I/P/R/Wh/mAh/CPU/MOS/FAN. Byte offsets 35–38 неизвестны, нельзя объявлять их ETS без проверки. **CDC/CDCDC/CDxn и отдельное переключение коммутатора через HID не декодированы.**
- Официальный Windows HID-клиент и Tuya/Smart Life подтверждают дистанционные функции, но не документируют Linux API, DP-map Tuya, состояния реле и аварийный fail-safe.

## 2. Ревизии коммутатора: критично

По вскрытию и измерениям Kirich (2026-05-28):
- R1: простой MOSFET, неполное размыкание, сомнительная защита.
- R2: последовательный диод — значительное падение напряжения, сильный нагрев.
- **R3: два MOSFET + радиатор + предохранитель + ОУ/управление; полное размыкание и защита от переполюсовки по результатам стендового теста; около 2,8 Вт потерь при 20 А, MOSFET <70 °C.** Коммутация по плюсовой шине; минус — транзитный.
- **R4: упрощённая версия, снова диод последовательно, удалены второй MOSFET, радиатор и предохранитель.** Не считать эквивалентом R3. Даже отзывы продавца о 100 В / 20 А не показывают тепловой режим. Нельзя гарантировать модель/ревизию по одному артикулу XH-CDC-MK.
- На BW600 изменялась форма четырёхконтактного подключения; электрический порядок, по обзору, сохранён, но механическая совместимость отличается. BW150 также имеет ревизионные различия; узнавать соответствие отдельно.
- Для R3 автор не рекомендует полагаться на защиту от переполюсовки при АКБ/источнике более 50–55 В (может суммироваться напряжение). На 12-вольтовой свинцовой АКБ основная опасность всё равно неправильная коммутация, аварийный ток и температурные потери.
- У обзора есть предметная дискуссия о LM321 и корректности обратнополярной защиты; выводы о защите R3 считать **стендовыми, не сертифицированным fail-safe**.

## 3. Границы ПО и safety

- В драйвере PeeJay `load_on` вычисляется как `current_A > 0.05`, то есть **не физический readback ключа**; `load_off()` возвращает `True` даже после истечения settle timeout без достоверного подтверждения off. Для RD6018 BOT это может быть только команда, не доказательство отключения.
- Нельзя путать CDC как автономную последовательность BW600 с управляемыми BOT этапами MAIN/MIX. В интеграции BOT должен быть единственным владельцем зарядно-разрядного state machine. BW600 — управляемая нагрузка и наблюдатель, а XH — коммутатор; автономные циклы BW600 не должны состязаться за управление выходом RD6018.
- Внешняя температура ETS для термозащиты MIX требует проверки при **Load OFF** и коммутаторе OFF, в идеале независимого канала от BW600. USB связь/температура/Output должны иметь freshness и реальный feedback; потеря связи = безопасное состояние, не утверждать OFF из одного ACK.
- В аппаратной схеме учитывать общий отрицательный провод, отдельные силовые и измерительные пары, FET body diodes, пути обратного тока, выключение под током, поведение при потере питания BW600, потенциал на АКБ при отключённом заряднике, нагрев диода/R3 транзисторов и отдельную защиту проводки.
- Номинал 20 А относится к зарядному коммутатору, не к разрядному пределу 30–50 А, а 100 В относится к модулю (BW600 измеряет до 200 В). Не смешивать эти ограничения.

## 4. Не доказано — не использовать как admission

- Какая **фактическая ревизия** продаётся в конкретной карточке Ozon; изображения продавца и маркировка могут не соответствовать поставке.
- USB-команды для CDC/CDCDC, реле XH-CDC-MK, аварийного состояния и реального подтверждения коммутации.
- Надёжное чтение внешнего NTC по USB, особенно с электронной нагрузкой OFF.
- Режим питания после перезагрузки, отсутствие самопроизвольного ON, поведение XH при исчезновении управляющего питания/USB, межрежимная блокировка и точные тайминги.
- Возможность использовать текущий образ Python HID V2.0.5 на другой прошивке/варианте BW600 без повторного read-only USB capture.
- Проверка электрического монтажа/тока/переполюсовки без конкретной платы на столе.

## 5. Исходные материалы

1. Руководство BW600 (копия PDF документа изготовителя): https://www.rcscomponents.kiev.ua/datasheets/BW600_User_manual.pdf
2. Руководство модуля XH-CDC-MK (публикация с фото): https://manuals.plus/ae/1005012203011503
3. Kirich: оригинальный обзор BW600 с реальным CDC: https://www.kirich.blog/obzory/izmeritelnoe/1280-atorch-bw600-prodolzhenie-lineyki-nagruzok-dl24mp.html
4. Kirich: обзор ревизий XH с электрическими измерениями и комментариями: https://www.kirich.blog/obzory/tehnicheskie-obzory/1303-plata-kommutacii-dlya-nagruzok-atorch-serii-bw600.html
5. GitHub, подтверждённый публичный репозиторий реинжиниринга BW600 HID: https://github.com/PeeJay/Atorch_BW600 (README, atorch_bw600.py; main, 2026-06).
6. Руководство ATORCH Windows PC software: https://manuals.plus/m/2bb657bf4d286eab7b068c4ee7aec41f080e8d7e28a08f0d205e9e76df0342e3
7. Ozon, пользовательская карточка (без верификации ревизии): https://www.ozon.ru/product/adapter-modulya-upravleniya-zaryadkoy-elektronnogo-nagruzochnogo-izmeritelya-bw600-4996377529/features/

**Вывод:** концепция RD6018 → XH-CDC-MK / BW600 → АКБ реализуема как штатный CDC-стенд; для полного программного цикла под владельцем RD6018 BOT имеются подтверждённые базовые CC HID-команды, но нет подтверждённого независимого readback ключа, remote relay protocol и ETS. Предпочтительнее XH revision 3, четвёртую ревизию нельзя принимать как такую же по качеству. Следующий безопасный этап — фото фактических плат, точная ревизия, read-only USB descriptor/telemetry capture без АКБ и load-on, затем электрические испытания на отдельном ограниченном источнике с независимой защитой. **Никакого монтажа и deploy на node104.**


## 2026-11-09 — DL24EW vs BW600 full decision comparison (same delivered price)

Owner's decision: compare at equal price for RD6018 BOT + lead-acid Ca/Ca/EFB/AGM restoration; charge source up to 18 V / 5 A (90 W); controlled discharge, BRT, ETS external NTC and possible charging switch. **Research only, no node104/deploy/actuation.**

**Hardware generation:** DL24EW is old DL24MP platform (display integrated), BW600 is new BW150 platform (separate display). Kirich teardown: BW600 adds two DAC arrangement vs previous DAC/multiplexer, hardware-assisted CV, better differential voltage sensing, higher-power current shunt, startup gate-suppression hardware, improved output-module current sharing. DL24EW software CV and shunt overheating observed at ~24 A; BW600 expansion configurations had current spikes that were later firmware/hardware adjusted. Kirich comments in 2026 report latest BW600 heatsinks cause ~10–15 C higher transistor temperature than earlier units. Neither 150 W base device requires power expansion at 12 V / 5–10 A discharge, assuming thermal test.

**Autonomous charging:** Kirich 2023 DL24EW CDC test found charge ended at voltage threshold without taper-current CV completion; he called CDC not suitable for accurate battery cycling as tested. 2025 BW600 CDC explicitly has maximum charge voltage and minimum charge-current termination settings, verified by live source/battery test. A later DL24EW firmware fix was not established. The BW600 external RD6018 still must provide actual CC/CV regulation; BW600 controls connection and termination, not RD charge current. Both use optional external charge switch module; DL24EW bundle sometimes includes it, not literally on the main board. BW600 CDC, CDCDC, CDxn (up to 99 cycles), DL24EW CDC/CDCDC; CDxn for DL24EW not evidenced.

**Switch hardware:** Kirich 2023 early DL24EW CDCMK IRFP264 low-side series MOSFET with radiator+fuse+isolated gate module. His measured drop across first old switching board at 5 A ≈ 0.20 V (≈1 W); later old-generation diode board at 5 A ≈ 0.55 V (≈2.75 W); first board intrinsic MOSFET body diode can permit reverse battery current toward charger while supposedly off. This is NOT a certified isolated switch. Distinguish those observations from BW600 XH-CDC-MK r4: diode series but 5 A voltage drop/heat have NOT been measured on concrete r4, assume 0.3–0.7 V only as scenarios = 1.5–3.5 W. R3 has full isolation in Kirich test; currently old stock scarce; connector mismatch between much older r1/r2 and current BW600. Low-side switch requires special care for common ground; high-side switch is not a proof of independent off.

**BRT and telemetry:** both support BRT, Kelvin four-wire U/I sensing, mAh, Wh, outside NTC and external-temperature limits. 2023 Kirich DL24EW BRT test used 1.8 A small battery and 18 A large battery, DC pulse result and estimated AC result; neither is four-terminal high-frequency battery impedance. BW600 exact BRT pulse algorithm and BRT invocation over USB unverified. For lead-acid recovery, compare only matched SOC/temp/pulse current/duration and wiring. Both ETS are visible in local UI; no validated ETS readback in published DL24EW or BW600 remote driver while load is OFF.

**Linux control:** DL24EW PC link is 3.3 V TTL via USB–UART dongle (Kirich notes no galvanic isolation). Generic older DL24P FF55 UART Python projects tshaddack/dl24, dimas/DL24-python are useful but NOT proven command-complete for DL24EW and unknown for CDC relay/BRT. BW600 BW-600W-DK V2.0.5 USB HID protocol independently reverse engineered in github.com/PeeJay/Atorch_BW600 (VID:PID 0483:5750, 64-byte reports, 0x47 CC, 0x48 CV, 0x49 CR, 0x4A CP, 0x21 setpoint, 0x25 load on/off, 0x03 and 0x05 status). Missing CDC/XH control, authentic switch readback and ETS. Published `load_off` may return true without physical confirmation; `load_on` state is inferred from measured I > 0.05 A; can't be used as safety interlock. USB HID also does not imply isolation. WiFi/Tuya for both is less desirable as primary control due to external/cloud dependence.

**Recommendation at equal cost:** BW600 150 W + XH-CDC-MK r4 preferred for product functionality, current-taper automatic CDC and better BW600-specific USB foundation, provided **actual** r4 5 A heat/diode-drop test and independent charge-break validation PASS. DL24EW bundled CDCMK is legitimate alternate if firmware current-taper cut-off is demonstrated and low-side reverse/current-path issues are mitigated and verified; not automatic winner merely from radiator. For BOT-owned programs, do not run autonomous CDC state machine concurrently: RD6018 BOT maintains single owner; BW600 would be isolated provider of discharge/measurements. Do not assume an operational remotely controlled charge relay until its protocol and readback are verified. Do not replace independent MIX battery temperature safeguards with unproved USB ETS.

**Source links:**
- https://www.kirich.blog/obzory/izmeritelnoe/1169-elektronnaya-nagruzka-atorch-dl24ew.html (DL24EW teardown/CDC/BRT and switch, 2023)
- https://www.kirich.blog/obzory/izmeritelnoe/1280-atorch-bw600-prodolzhenie-lineyki-nagruzok-dl24mp.html (BW600 teardown, CDC/current cut, 2025; 2026 owner comments)
- https://www.kirich.blog/en/stati/moi-proekty/1267-plata-zaschity-i-kommutacii-zaryadnogo-ustroystva-dlya-nagruzok-atorch.html (old switch 5 A measured drops/body diode)
- https://www.kirich.blog/en/reviews/technical-reviews/1303-atorch-bw600-load-switching-board.html (R3/R4)
- https://manuals.plus/ae/1005005866012922 (DL24EW manual)
- https://manuals.plus/m/dcb614f6ba219a12e1665334be45b8923902366085acc539575666b0b682de37 (BW600 manual)
- https://github.com/PeeJay/Atorch_BW600 (specific BW600 HID)
- https://github.com/tshaddack/dl24 (older UART protocol with device compatibility caveat)
