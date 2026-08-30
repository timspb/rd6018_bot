# RD6018 Telegram Operator HMI — Storyboard / Wireframes

Status: **DESIGN REVIEW INPUT — NOT IMPLEMENTATION**

This file is the concrete screen-by-screen companion to `OPERATOR_HMI_SPEC.md`.

The text below is intentionally close to what the operator would actually see. Internal identifiers and implementation details are omitted unless the screen is explicitly a technical-detail view.

Button style notation:

```text
[ primary: ... ]
[ success: ... ]
[ danger: ... ]
[ ... ]             # neutral/default
```

For classic HTML/InlineKeyboard fallback, the style annotation is semantic only; button order and wording remain the same.

---

# 1. IDLE — healthy / ready

## L2 panel

```text
RD6018 · ГОТОВ

Output OFF

АКБ                 12.71 V
Температура          24.3°C
БП                   37.8°C

Защита: норма
Связь: RD ✓  ESP ✓  HA ✓

Последняя АКБ
Varta Silver Dynamic · AGM 70 Ah
```

Buttons:

```text
[ primary: Новая программа ]
[ Ручной режим ] [ График ]
[ АКБ ]          [ Ещё ]
```

Notes:

- no graph-range buttons on L2;
- no controller-debug button on L2;
- no permanent Manual-OFF button unless a condition is armed;
- chemistry is plain text, not a red/orange/blue severity badge.

---

# 2. IDLE — advisory present

Example: rest observation recommended after heavy recovery.

```text
RD6018 · ГОТОВ

Output OFF
АКБ 12.76 V · 24.1°C

Рекомендация
Полезно оставить АКБ в покое для контрольного замера через 24 ч.
Это не блокирует новый заряд.

Защита: норма
```

Buttons unchanged.

No push alarm is required for a passive recommendation.

---

# 3. New Program — choose physical battery

L4/workspace:

```text
НОВАЯ ПРОГРАММА

Что сейчас подключено?
```

Buttons:

```text
[ Varta Silver Dynamic · AGM 70 Ah ]
[ Exide EL752 · EFB 75 Ah ]
[ Другая АКБ ]

[ Назад к панели ]
```

If there is only one registered likely battery, it may appear first but must not be silently auto-selected.

---

# 4. New Program — registered battery selected

```text
Varta Silver Dynamic
AGM · 70 Ah

Сейчас
12.63 V · 24.1°C
Output OFF

Выберите программу
```

Buttons:

```text
[ primary: Обычный заряд ]
[ Восстановление ]
[ Кондиционирование ]
[ Диагностика ]
[ Авто Mix ]

[ Другая АКБ ] [ Отмена ]
```

Normal is visually primary because it is the ordinary product path.

Recovery/Conditioning are not red or alarming merely because they can use higher voltage.

---

# 5. New Program — ad-hoc chemistry

```text
ДРУГАЯ АКБ

Выберите тип
```

Buttons:

```text
[ Ca/Ca ] [ EFB ] [ AGM ]
[ Flooded ]
[ Назад ]
```

No colored chemistry squares.

Next screen:

```text
EFB

Введите ёмкость, Ah
Например: 75
```

Then program selection as in screen #4.

---

# 6. NORMAL preview

```text
ОБЫЧНЫЙ ЗАРЯД

Varta Silver Dynamic
AGM · 70 Ah

Старт: MAIN
Основной профиль:
14.4 → 14.6 → 14.8 → 15.0 V
I max: 7.0 A

Штатная автоматическая цепочка:
Recovery/Mix могут использоваться только по критериям V2.
Mix: до 16.3 V · стандартный ограниченный ток

АКБ: 24.1°C
Output сейчас OFF
Готовность: подтверждена
```

Buttons:

```text
[ success: ЗАПУСТИТЬ ]
[ Изменить программу ] [ Отмена ]
[ Почему такие параметры? ]
```

`Почему такие параметры?` opens a collapsible/details block or detail screen with threshold/rationale information.

Normative semantic correction:

> Normal is **not** described as “без автоматического HV/Mix”.

---

# 7. RECOVERY preview

```text
ВОССТАНОВЛЕНИЕ

Varta Silver Dynamic
AGM · 70 Ah

Старт: MAIN
Recovery разрешён только при подтверждённом V2 evidence.

Основной профиль:
14.4 → 14.6 → 14.8 → 15.0 V

Recovery/Mix ceiling:
до 16.3 V

Диагностический HV-veto: нет
АКБ: 24.1°C
Output OFF
```

Buttons:

```text
[ success: ЗАПУСТИТЬ ]
[ Изменить программу ] [ Отмена ]
[ Подробнее о Recovery ]
```

If diagnostic authority blocks automatic HV, preview must say so before Start:

```text
Внимание
Автоматический Recovery/Mix сейчас заблокирован диагностикой.
Программа может выполнять только разрешённые безопасные этапы.
```

The Start action must not promise unavailable behavior.

---

# 8. DIAGNOSTIC preview

```text
ДИАГНОСТИКА

Varta Silver Dynamic
AGM · 70 Ah

Автоматическая HV-эскалация: ЗАПРЕЩЕНА

Доступны:
• безопасный основной заряд/наблюдение в разрешённом envelope
• анализ U/I/T
• сохранение диагностического evidence

АКБ: 24.1°C
Output OFF
```

Buttons:

```text
[ success: ЗАПУСТИТЬ ]
[ Отмена ]
[ Что будет измеряться? ]
```

---

# 9. AUTO MIX preview

```text
АВТО MIX

Exide EL752
EFB · 75 Ah

Старт сразу с Mix
PREP/Main/Recovery пропускаются.

Требование старта:
Vbat ≥12.0 V

Цель Mix:
16.5 V
I limit: стандартный Mix (~0.03C, в пределах hardware cap)

Финиш:
CV: Imin → ΔI
CC: Vmax → ΔV
3 подтверждения → выдержка 2 ч

АКБ: 12.71 V · 25.0°C
Output OFF
```

Buttons:

```text
[ success: ЗАПУСТИТЬ AUTO MIX ]
[ Отмена ]
[ Подробнее ]
```

If Vbat <12.0 V:

```text
АВТО MIX НЕДОСТУПЕН

Vbat: 11.72 V
Минимум для прямого Mix: 12.0 V

Автоматика не будет скрыто переходить в PREP.
Выберите обычный заряд.
```

Buttons:

```text
[ primary: Обычный заряд ]
[ Назад ]
```

---

# 10. STARTING — command accepted, not yet physically verified

The preview card should transition or be replaced with:

```text
ЗАПУСК...

Varta AGM 70 Ah · Обычный заряд

✓ Safety preflight
✓ OVP/OCP programmed
✓ V/I programmed
✓ Readback confirmed
… Edge lease / Output ON verification

Output: ещё не подтверждён
```

Buttons:

```text
[ Подробнее ]
```

Do not expose a second Start button.

If the operation takes long enough for the user to wonder whether the tap worked, this state is mandatory.

---

# 11. START FAILED — safe outcome

```text
ЗАПУСК НЕ ВЫПОЛНЕН

Причина:
не подтверждён readback тока

Output OFF подтверждён.
Уставки не считаются активной программой.
```

Buttons:

```text
[ primary: Повторить с новой проверкой ]
[ К панели ]
[ Технические детали ]
```

---

# 12. START FAILED — containment

```text
🚨 СОСТОЯНИЕ OUTPUT НЕ ПОДТВЕРЖДЕНО

Запуск прерван.
Команда OFF отправлена, но RD6018 не подтвердил физическое отключение.

Защитный контур продолжает попытки отключения.

Не запускайте новую программу.
```

Buttons:

```text
[ primary: Подробнее ]
[ Диагностика связи ]
```

No Start, Manual V/I or reconfigure control.

---

# 13. PREP — active

```text
RD6018 · Varta AGM 70 Ah · Обычный заряд

ПОДГОТОВКА · CC                  0ч 18м
Output ON

11.94 V        0.70 A        8 W
АКБ 24.7°C     БП 37.9°C

Низкое стартовое напряжение.
Идёт малотоковая подготовка перед MAIN.

Цель: ~12.0 V · 0.01C

Защита: норма
Связь: RD ✓  ESP ✓  HA ✓
```

Buttons:

```text
[ danger: Остановить заряд ]
[ primary: Подробнее ]
[ График ] [ Ещё ]
```

---

# 14. MAIN — CC

```text
RD6018 · Varta AGM 70 Ah · Обычный заряд

ОСНОВНОЙ ЗАРЯД · CC             1ч 42м
Output ON

14.21 V        6.96 A       99 W
АКБ 26.2°C     БП 41.3°C

Цель: 14.40 V · ≤7.0 A
Напряжение растёт штатно.

Защита: норма
Связь: RD ✓  ESP ✓  HA ✓
```

Same L2 buttons.

---

# 15. MAIN — CV, normal tail

```text
RD6018 · Varta AGM 70 Ah · Обычный заряд

ОСНОВНОЙ ЗАРЯД · CV             5ч 12м
Output ON

14.80 V        1.14 A       17 W
АКБ 27.4°C     БП 39.6°C

Ток снижается.
Формируется зарядный хвост.

Защита: норма
```

No Imin threshold dump on L2.

`Подробнее` opens screen #16.

---

# 16. MAIN detail — CV evidence

```text
ОСНОВНОЙ ЗАРЯД · ДЕТАЛИ

Режим: CV
Уставка: 14.80 V / 7.0 A max

Ток
Imin                    0.412 A
Текущий                 0.437 A
ΔI от Imin             +0.025 A
Порог reversal          0.124 A
После Imin                 37м

Температура
27.4°C · +0.01°C/мин

Решение автоматики
Продолжать заряд
```

Buttons:

```text
[ К панели ]
[ График ] [ События этапа ]
```

This is where detailed evidence belongs.

---

# 17. Recovery stage

```text
RD6018 · Varta AGM 70 Ah · Восстановление

ВОССТАНОВИТЕЛЬНЫЙ ЭТАП · CV     0ч 36м
Output ON

16.30 V        1.38 A       23 W
АКБ 28.1°C     БП 39.7°C

Ограниченный восстановительный этап.
Попытка 2 из 4 для этой сессии.

Защита: норма
```

Avoid wording that claims sulfation has definitely been removed.

---

# 18. MIX — searching for finish evidence

```text
RD6018 · Exide EFB 75 Ah · Обычный заряд

MIX · CV                         3ч 08м
Output ON

16.48 V        0.62 A       10 W
АКБ 30.1°C     БП 40.0°C

Формируется Imin.
Финишный критерий ещё не подтверждён.

Контрольное окно: до 24 ч
Защита: норма
```

---

# 19. MIX — finish evidence confirmed, sticky hold

```text
RD6018 · Exide EFB 75 Ah · Обычный заряд

MIX · CV                         8ч 17м
Output ON

16.46 V        0.47 A
АКБ 30.1°C

✓ Финишный критерий подтверждён
Финальная выдержка: 0ч 43м / 2ч 00м

Защита: норма
```

This is more useful to an operator than showing a raw `finish_hold_started_at` timestamp.

---

# 20. SAFE_WAIT

```text
RD6018 · Exide EFB 75 Ah · Обычный заряд

БЕЗОПАСНОЕ ОЖИДАНИЕ             0ч 24м
Output OFF

АКБ 13.17 V · 27.9°C

Наблюдение релаксации после этапа.
Продолжение произойдёт автоматически по условиям
или не позднее максимального окна ожидания.

Защита: норма
```

Buttons:

```text
[ danger: Остановить программу ]
[ primary: Подробнее ]
[ График ] [ Ещё ]
```

No generic `Включить` button.

---

# 21. COOLING — no operator action required

Push/L1 when entering:

```text
⚠️ ТЕРМОПАУЗА

АКБ достигла 40.2°C.
Output OFF подтверждён.

Автоматика ждёт охлаждения до ≤35°C.
Действие оператора: не требуется.
```

L2:

```text
RD6018 · Exide EFB 75 Ah · Обычный заряд

⚠ ТЕРМОПАУЗА
Output OFF

АКБ 40.2°C → ждём ≤35.0°C
БП 42.1°C

Текущий этап будет продолжен после безопасного охлаждения.
Таймеры активного этапа заморожены.
```

Buttons:

```text
[ danger: Остановить программу ]
[ primary: Подробнее ]
[ График ]
```

No “Resume now”.

---

# 22. COOLING — sensor/condition prevents resume

```text
🚨 ПРОДОЛЖЕНИЕ ЗАБЛОКИРОВАНО

Термопауза активна.
Output OFF подтверждён.

Температура АКБ сейчас недоступна.
Автоматическое продолжение невозможно без свежего temp_ext.

Требуется:
проверить датчик температуры АКБ.
```

Buttons:

```text
[ primary: Диагностика связи/датчика ]
[ Остановить программу ]
```

---

# 23. STORAGE — completed normal charge, Output ON

Push/L1:

```text
✓ ЗАРЯД ЗАВЕРШЁН
Varta AGM 70 Ah перешла в режим хранения.
Output остаётся ON: 13.8 V / 1.0 A.
```

L2:

```text
RD6018 · Varta AGM 70 Ah

ЗАРЯД ЗАВЕРШЁН · ХРАНЕНИЕ
Output ON

13.80 V        0.41 A
АКБ 25.2°C

Режим хранения: 13.8 V / 1.0 A
Защита: норма
```

Buttons:

```text
[ danger: Отключить Output ]
[ primary: Итоги сессии ]
[ График ] [ Ещё ]
```

This screen exists specifically to prevent the semantic error “Done == OFF”.

---

# 24. Normal operator Stop confirmation

Tap `Остановить заряд` from healthy running state.

```text
ОСТАНОВИТЬ ПРОГРАММУ?

Varta AGM 70 Ah
MAIN · CV
14.80 V · 1.14 A

После подтверждения будет выполнен verified OFF.
```

Buttons:

```text
[ danger: ОСТАНОВИТЬ ]
[ Продолжить заряд ]
```

---

# 25. STOPPING

Immediately after confirmed user action:

```text
ОСТАНОВКА...

Команда OFF отправлена.
Ожидание подтверждения RD6018.

Output: ещё не подтверждён OFF
```

Buttons:

```text
[ Подробнее ]
```

No Start/reconfigure buttons.

---

# 26. Stop success

```text
✓ ПРОГРАММА ОСТАНОВЛЕНА

Output OFF подтверждён.
Сессия завершена пользователем.
```

Buttons:

```text
[ primary: К панели ]
[ Итоги сессии ]
```

---

# 27. OFF unconfirmed containment

L1 + L2 high attention:

```text
🚨 OFF НЕ ПОДТВЕРЖДЁН

Команда отключения отправлена,
но физическое состояние RD6018 не подтверждено.

Защитный контур продолжает попытки OFF.
Новые команды включения и изменения уставок заблокированы.

Последнее известное:
Vout 14.81 V
I 1.02 A
```

Buttons:

```text
[ primary: Технические детали ]
[ Диагностика связи ]
```

No button that can energize/reconfigure output.

When containment resolves:

```text
✓ Output OFF подтверждён.
Защитное состояние снято.
```

---

# 28. Hardware trip — OVP/OCP/OPP

Example OPP:

```text
🚨 СРАБОТАЛА ЗАЩИТА OPP

Output OFF подтверждён.
Программа остановлена защитным контуром.

Факт перед отключением:
14.76 V · 8.3 A · 123 W
АКБ 28.4°C · БП 44.0°C

Требуется:
проверить нагрузку/настройки/подключение перед новым запуском.
```

Buttons:

```text
[ primary: Диагностика ]
[ События ]
[ К панели ]
```

There is no Start button directly on the trip alarm card.

---

# 29. Stale HA telemetry protective stop

```text
🚨 ТЕЛЕМЕТРИЯ УСТАРЕЛА

Свежие данные АКБ не получены вовремя.
Output OFF подтверждён.
Программа заморожена/остановлена согласно safety policy.

Источник:
температура АКБ / battery voltage / current

Требуется:
проверить ESPHome / Home Assistant / сеть.
```

Buttons:

```text
[ primary: Диагностика связи ]
[ Технические детали ]
```

Technical detail may show exact source timestamp/age/skew.

---

# 30. Communications detail

```text
СВЯЗЬ / SAFETY PATH

RD6018 Modbus       ✓ свежо
ESPHome             ✓ online
Edge lease          ✓ armed · generation 182
Home Assistant      ✓ API

Battery voltage     1.2 s
Current             1.1 s
Temp АКБ            2.0 s
Output state        0.8 s
Protection code     1.0 s
Regulation mode     1.0 s

V/I/OVP/OCP readback
последняя transaction: подтверждена
```

Buttons:

```text
[ К панели ]
[ Сырые entity details ]
```

This screen is L3 and may contain developer/technical terms.

---

# 31. Manual — setup

```text
РУЧНОЙ РЕЖИМ

Введите требуемые V и I.
Система сама рассчитает OVP/OCP.

Пределы:
V ≤17.5 V
I ≤12.0 A
```

After input `14.6 5.0`:

```text
РУЧНОЙ РЕЖИМ · PREVIEW

Задано оператором
V       14.60 V
I        5.00 A

Рассчитано системой
OVP     14.70 V
OCP      5.10 A

АКБ для истории: Varta AGM 70 Ah
(тип/ёмкость АКБ не изменяют V/I)

Output OFF
```

Buttons:

```text
[ success: ВКЛЮЧИТЬ MANUAL ]
[ Добавить условие OFF ]
[ Изменить V/I ] [ Отмена ]
```

---

# 32. Manual — active

```text
RD6018 · РУЧНОЙ РЕЖИМ

Output ON                         0ч 37м

14.60 V        4.82 A       70 W
АКБ 26.4°C     БП 40.3°C

Задано: 14.60 V / 5.00 A
Защита: OVP 14.70 V / OCP 5.10 A

Условие OFF:
I достигнет 0.50 A
```

Buttons:

```text
[ danger: Остановить Manual ]
[ primary: Изменить V/I ]
[ Условие OFF ] [ Подробнее ]
```

---

# 33. Manual — Cooling

```text
⚠ РУЧНОЙ РЕЖИМ · ТЕРМОПАУЗА

Output OFF подтверждён.
АКБ 40.1°C → ждём ≤35.0°C

Запрошенные параметры сохранены:
14.60 V / 5.00 A

После охлаждения они будут применены только через новую safety/readback transaction.
```

Buttons:

```text
[ danger: Завершить Manual ]
[ Подробнее ]
```

No force-resume button.

---

# 34. Manual interrupted after restart

```text
ПРЕРВАННЫЙ MANUAL

До перезапуска было запрошено:
14.60 V / 5.00 A
OVP 14.70 V / OCP 5.10 A

АКБ: Varta AGM 70 Ah

Output НЕ будет включён автоматически.
Для продолжения нужна новая полная проверка.
```

Buttons:

```text
[ primary: Проверить и запустить заново ]
[ Удалить запрос ]
[ Технические детали ]
```

Reauthorize opens a fresh preview, not an immediate ON.

---

# 35. Manual-OFF armed in AUTO

Normal active L2 adds one non-alarm line:

```text
Доп. условие OFF: I ≤0.20 A
```

It must **not** say that AUTO strategy is paused or overridden.

Detail screen:

```text
УСЛОВИЕ OFF

I ≤0.20 A

Это дополнительный terminal stop.
Пока условие не выполнено, автоматическая стратегия Recovery/Mix работает штатно.
```

When condition triggers:

```text
ОСТАНОВКА ПО УСЛОВИЮ
I ≤0.20 A выполнено.

... STOPPING until OFF proof ...
```

After OFF proof the condition is retired according to the accepted runtime contract.

---

# 36. Diagnostic summary — no immediate concern

```text
ДИАГНОСТИКА АКБ

Varta AGM 70 Ah

Итог: наблюдение
Автоматический HV-veto: нет

Доступные evidence:
• relaxation history
• recovery response
• temperature behavior
• capacity/CCA history

Плотность: не применяется для AGM
```

Buttons:

```text
[ Подробные hypotheses ]
[ История ]
[ К панели ]
```

---

# 37. Diagnostic summary — VERIFY state

```text
⚠ ТРЕБУЕТСЯ ПРОВЕРКА

Exide EFB 75 Ah

Причина:
побаночный SG-разброс сохраняется после corrective cycle.

Автоматический HV:
пока не запрещён только по одному этому признаку.

Рекомендуется:
повторить SG после корректного полного заряда/отстоя
и сопоставить с другими evidence.
```

Buttons:

```text
[ primary: Ввести SG ]
[ Evidence ]
[ К панели ]
```

---

# 38. Diagnostic — BLOCK_AUTOMATIC_HV

```text
🚨 АВТОМАТИЧЕСКИЙ HV ЗАБЛОКИРОВАН

Причина:
сильное независимое evidence риска дефектной банки.

Это диагностический запрет новой HV-эскалации.
Он не является самостоятельным физическим HARD_STOP.

Output: OFF
```

Buttons:

```text
[ primary: Evidence ]
[ Внешние измерения ]
[ К панели ]
```

The operator cannot bypass this via a generic `expert` button.

---

# 39. Battery registry — list

```text
АККУМУЛЯТОРЫ

Varta Silver Dynamic
AGM · 70 Ah · состояние: healthy

Exide EL752
EFB · 75 Ah · требуется SG retest
```

Buttons ideally one battery per row:

```text
[ Varta AGM 70 Ah ]
[ Exide EFB 75 Ah ]
[ Добавить АКБ ]
[ К панели ]
```

Do not compress chemistry into severity colors.

---

# 40. Battery card

```text
VARTA SILVER DYNAMIC
AGM · 70 Ah
ID: varta70

Состояние: исправная
Последний полный цикл: 6 дней назад

Последние измерения
Ёмкость       61 Ah
CCA          610 A
Ri*          6.3 mΩ

* внешнее измерение, если оно действительно было внешним
```

Buttons:

```text
[ primary: Зарядить ]
[ История ] [ Диагностика ]
[ Изменить ]
[ Назад ]
```

If the stored `Ri` came from a true external test, label its provenance. Do not relabel the two-wire dynamic-loop metric as battery Ri.

---

# 41. SG input — native fallback

Eligibility has already been checked by D053 policy.

```text
ПЛОТНОСТЬ ПО БАНКАМ

Exide EFB 75 Ah
Доступ к электролиту: SERVICEABLE

Введите 6 значений слева направо.
Для недоступной банки используйте `-`.

Пример:
1.278 1.276 1.275 1.274 1.277 1.276

Дополнительно можно указать температуру/контекст согласно формату.
```

After parse:

```text
SG ЗАПИСАНА

1   1.278
2   1.276
3   1.275
4   1.274
5   1.277
6   1.276

Spread: 0.004
Оценка: выраженного побаночного дисбаланса нет
```

Buttons:

```text
[ Сохранить/готово ]
[ Ввести заново ]
[ Политика коррекции ]
```

A future Mini App may replace the text form but native fallback remains.

---

# 42. Graph workspace

```text
ГРАФИК · ТЕКУЩАЯ СЕССИЯ

[chart/image]

Метки:
00:00 MAIN
05:12 CV
08:45 Recovery
10:45 SAFE_WAIT
12:03 MAIN
17:20 MIX
```

Buttons:

```text
[ 30 мин ] [ 2 часа ] [ Сессия ]
[ К панели ]
[ События ]
```

Alarm markers should be visible on the plot when technically feasible.

---

# 43. Events — operator view

```text
СОБЫТИЯ · СЕССИЯ

18:42  MAIN → MIX
       normal tail complete

16:38  SAFE_WAIT → MAIN
       relaxation window complete

14:37  Recovery → SAFE_WAIT
       recovery window complete

12:37  MAIN → Recovery
       stable CV plateau confirmed
```

Buttons:

```text
[ Только важные ] [ Все технические ]
[ К панели ]
```

Warnings/trips get clear symbols/text; normal transitions remain neutral.

---

# 44. More menu

Active:

```text
ЕЩЁ
```

```text
[ АКБ ] [ События ]
[ Диагностика ] [ Контроллер ]
[ Условие OFF ]
[ К панели ]
```

Idle:

```text
[ АКБ ] [ События ]
[ Диагностика ] [ Контроллер ]
[ Настройки/служебное ]
[ К панели ]
```

This menu is intentionally low-frequency.

---

# 45. Rich Message L2 candidate layout

Conceptual structure, not exact Telegram markup:

```text
# RD6018 · Varta AGM 70 Ah

## MAIN · CV · 5ч 12м
Output ON

| АКБ | Ток | Темп. АКБ |
| --- | --- | --- |
| 14.80 V | 1.14 A | 27.4°C |

Ток снижается · формируется зарядный хвост

Защита: норма
Связь: RD ✓ · ESP ✓ · HA ✓

[ danger: Остановить заряд ]
[ primary: Подробнее ]
[ link/default: График ] [ link/default: Ещё ]

<details>
<summary>Техническое состояние</summary>
Imin/Δ/readback/lease details...
</details>
```

Safety-critical buttons must be placed in a simple dedicated button row, not inside a table-cell interaction.

---

# 46. Classic HTML fallback L2

The same semantics without Rich Messages:

```text
<b>RD6018 · Varta AGM 70 Ah</b>

<b>MAIN · CV</b> · 5ч 12м
Output ON

<b>14.80 V</b>   <b>1.14 A</b>   27.4°C
Ток снижается · формируется зарядный хвост

Защита: норма
Связь: RD ✓ · ESP ✓ · HA ✓
```

Classic InlineKeyboard:

```text
[ 🛑 Остановить заряд ]
[ Подробнее ]
[ График ] [ Ещё ]
```

Meaning and ordering stay identical to Rich Message version.

---

# 47. Renderer/client failure behavior

If Telegram edit/rich rendering fails after a successful actuator action:

- actuator result remains authoritative;
- UI error is logged;
- bot sends a fallback status message if possible;
- never roll back/repeat hardware action just because rendering failed.

Example fallback:

```text
Статус панели не удалось обновить.

Физическое состояние:
Output OFF подтверждён.
Программа остановлена.

Обновите панель позже.
```

---

# 48. Minimum navigation depth target

From L2:

```text
Status detail     1 tap
Graph             1 tap
Stop              1 tap + confirm
Battery list      2 taps max via More, or 1 from idle
Events            2 taps max via More
Diagnostics       2 taps max via More
```

During an active alarm, the relevant detail/action should become one tap from the alarm/L2 banner.

---

# 49. State/button matrix

| State | Dominant action | Start exposed? | Stop exposed? | Reconfigure exposed? |
|---|---|---:|---:|---:|
| IDLE | New Program | yes | no | no |
| STARTING | none / Details | no | safety-owned cancellation only if defined | no |
| RUNNING AUTO | Stop | no | yes | no |
| RUNNING MANUAL | Stop Manual | no | yes | Manual reconfigure |
| SAFE_WAIT | Stop Program | no | yes | no |
| COOLING | Stop Program | no | yes | no |
| STOPPING | Details | no | no duplicate Stop | no |
| STORAGE | Disable Output | no | yes | no |
| CONTAINMENT | Details/Diagnostics | **no** | safety retry automatic | **no** |
| TRIPPED | Diagnostics | no | already safety-off | no |
| INTERRUPTED | Re-authorize / discard | no immediate ON | no | fresh preview only |

---

# 50. Alarm/state wording matrix

| Internal concept | L2/operator wording |
|---|---|
| `STAGE_PREP` | Подготовка |
| `STAGE_MAIN` | Основной заряд |
| `STAGE_DESULFATION` | Восстановительный этап |
| `STAGE_MIX` | Mix |
| `STAGE_SAFE_WAIT` | Безопасное ожидание |
| `STAGE_COOLING` | Термопауза |
| `STAGE_DONE` with storage ON | Заряд завершён · Хранение |
| `manual` | Ручной режим |
| `output_off_unconfirmed` | OFF не подтверждён |
| `telemetry_invalid/stale` | Телеметрия недоступна/устарела |
| `BLOCK_AUTOMATIC_HV` | Автоматический HV заблокирован |
| `authoritative=True` | normally hidden; technical detail only |
| `decision=continue` | Заряд продолжается / relevant semantic progress |

---

# 51. Design review questions before implementation

These are deliberate review points, not implementation questions to decide silently:

1. Is normal Stop confirmation desired every time, or should a long-press-like second tap pattern be simulated instead? Current recommendation: explicit confirmation.
2. Should Storage notification be sent every completion or be user-configurable? Recommendation: send once; it is meaningful and clarifies Output remains ON.
3. Should `Recovery` and `Conditioning` both remain first-level program choices, or should Conditioning move under `Ещё` for ordinary use? Recommendation: keep during V2 validation, revisit after real usage.
4. Should Auto Mix remain first-level? Recommendation: yes, because it is an explicitly requested distinct operational mode.
5. Should battery selection precede program selection? Recommendation: yes for registered batteries because chemistry/Ah/diagnostic history become deterministic.
6. Should primary L2 show power? Recommendation: keep initially; remove later if it does not influence operator decisions.
7. Should PSU temperature be always visible? Recommendation: compact secondary value while normal; promote only when abnormal.
8. Should the technical `V2 controller` screen remain? Yes, but rename to `Контроллер · детали` and keep at L3.
9. Should private-chat topics be used? Recommendation: no for first redesign; solve hierarchy with panel/workspaces first.
10. Should Mini App be implemented immediately? Recommendation: no; first native Rich/HTML HMI, then Mini App for analytics/forms if still justified.

---

# 52. Implementation sequence after storyboard approval

Do not implement screens opportunistically. Preferred order:

```text
1. semantic OperatorHmiState adapter
2. renderer-independent screen/view models
3. classic HTML renderer parity tests
4. L2 idle/running/paused/storage/containment
5. Start/Stop L4 command lifecycle
6. detail/graph/more workspaces
7. alarm rationalization layer
8. battery/manual/diagnostic workspaces
9. Rich Message renderer behind feature flag
10. Android/Desktop client rendering/interaction matrix
11. optional Mini App spike
```

At each step controller/safety tests remain unchanged; HMI tests assert presentation and callback authority only.
