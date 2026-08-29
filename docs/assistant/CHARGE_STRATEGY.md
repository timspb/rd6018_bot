# Charge Strategy Reference

Этот документ — короткий source of truth по production-стратегии заряда в V2.
Если есть сомнение в логике этапов, сначала смотри сюда, затем `production_controller.py`, `charge_controller_v2.py`, `v2_authority.py` и только потом legacy `charge_logic.py`.

## Главная модель

В V2 четыре независимых измерения:

- **chemistry**: AGM / EFB / Ca/Ca / Flooded / Custom;
- **intent**: Normal / Recovery / Conditioning / Diagnostic;
- **condition**: Unknown / Healthy / Sulfated suspected / Dry suspected / Rehydrated / Overwet suspected / Stratified suspected / Degraded;
- **stage**: Prep / Main / Desulfation / Mix / SAFE_WAIT / Cooling / Done.

`AGM + NORMAL` и `AGM + REHYDRATED + RECOVERY` — разные программы, даже если физическая химия одна.

## Production authority

- `ProductionChargeControllerV2` — live controller.
- `ChargeControllerV2` владеет решениями `Main`/`Mix` для всех non-Custom профилей.
- Legacy `ChargeController.tick()` используется как проверенный scaffold для telemetry validation, temperature safety, hard timeout, SAFE_WAIT/Cooling, restore и persistence, но его обычные `Main -> HV` и `Mix -> finish` триггеры маскируются при V2 authority.
- `V2_AUTHORITATIVE=0` — независимый аварийный rollback actuator-логики.
- `V2_UI=0` — rollback нового Telegram UI без отключения V2 actuator authority.
- Custom остаётся legacy-authoritative: это отдельный операторский контракт.

## Сигналы

- `temp_ext` — внешний датчик АКБ и единственная основная температура батареи.
- `temp_int` — температура блока/БП, используется только для защиты железа.
- `is_cv` — стабилизация напряжения: управляется U, поэтому независимый отклик АКБ читаем прежде всего по I (`Imin -> ΔI`).
- `is_cc` — стабилизация тока: управляется I, поэтому независимый отклик читаем по U (`Vmax -> ΔV`).
- Токовый CV-критерий нельзя переносить на CC.

`SignalAnalyzer` дополнительно вычисляет `dU/dt`, `dI/dt`, `dT/dt`, минимум/максимум, plateau и mode-specific reversal confirmations. Одиночный sample не является основанием для HV или финиша.

## Intent-specific цепочки

### Normal

```text
Prep -> Main -> SAFE_WAIT/Done
```

- автоматический HV/Mix запрещён;
- если Main-tail стабилен и выдержка завершена — штатное завершение без recovery HV;
- persistent abnormal plateau не конвертируется автоматически в повышенное напряжение: V2 останавливает автоэскалацию и требует диагностики.

### Diagnostic

Поведение по HV такое же консервативное, как Normal: автоматическая HV-эскалация запрещена. Цель — получить интерпретируемые evidence, а не «додавить» АКБ.

### Recovery / Conditioning

```text
Prep -> Main -> (Desulfation) -> Mix -> SAFE_WAIT -> Done/Storage
```

HV разрешён только после V2 evidence. Сам факт выбора AGM/EFB/Ca/Ca не разрешает Mix.

- Main-tail должен быть реально сформирован и выдержан;
- стабильная умеренная полка может разрешить сервисный Desulfation;
- полка выше примерно `1%C` не считается «обычным хвостом» и не переводится автоматически в HV;
- thermal instability / voltage instability / invalid telemetry прекращают автоэскалацию.

`Conditioning` без отдельного expert authorization использует тот же recovery voltage envelope. EFB 17.2–17.5 V не включается автоматически.

## Recipe envelope

`ProductionChargeControllerV2` ограничивает **каждую сгенерированную уставку после термокомпенсации** chemistry+intent envelope. Поэтому temperature compensation не может незаметно вывести этап выше разрешённой программы.

Текущие ceilings:

| Chemistry | Normal/Diagnostic | Recovery | Conditioning без expert |
|---|---:|---:|---:|
| AGM | 15.0 V | 16.3 V | 16.3 V |
| EFB | 14.8 V | 16.5 V | 16.5 V |
| Ca/Ca | 14.7 V | 16.5 V | 16.5 V |
| Flooded | 14.8 V | 16.5 V | 16.5 V |

Expert EFB envelope до 17.5 V существует в policy model, но production Telegram workflow его не авторизует автоматически.

## Термокомпенсация

Legacy formula остаётся источником базовой поправки:

```text
V_compensated = V_base + k * (25 - temp_ext)
```

- ref: 25°C;
- Ca/Ca, EFB: 0.018 V/°C;
- AGM: 0.016 V/°C;
- Custom: 0.018 V/°C;
- legacy delta clamp: ±0.60 V.

После расчёта V2 production layer дополнительно ограничивает результат recipe envelope текущего intent. На SAFE_WAIT/Cooling/Done/Idle компенсация не применяется.

## Профильные базовые targets

### Ca/Ca

- Main base: 14.7 V;
- Recovery Mix base: 16.5 V;
- Mix fallback observation window: 20 h.

### EFB

- Main base: 14.8 V;
- Recovery Mix base: 16.5 V;
- Mix fallback observation window: 20 h.

### AGM

- Main bases: 14.4 -> 14.6 -> 14.8 -> 15.0 V;
- переход на следующую AGM Main-ступень требует V2 tail evidence и выдержку;
- Recovery Mix base: 16.3 V;
- Mix fallback observation window: 10 h.

### Custom

- использует операторские уставки и отдельную legacy delta/time contract;
- V2 Pb recovery authority на Custom не распространяется.

## Main evidence

Вместо универсального абсолютного «0.2/0.3 A = готово» V2 нормализует tail относительно ёмкости АКБ.

- для Ca/Ca/EFB историческая логика соответствует примерно capacity-normalized tail;
- AGM также оценивается относительно C-rate;
- новый минимум сбрасывает возраст tail;
- только достаточно старый стабильный tail может разрешить следующий transition;
- высокий persistent plateau (>~1%C) не считается безопасным поводом автоматически поднять U.

## Mix: CV и CC — разные критерии

### CV

- фиксируется реальный `Imin`;
- кандидат финиша — подтверждённый рост `ΔI` от Imin;
- рабочая гипотеза threshold: `max(0.03 A, 30% от Imin)`;
- `I↑` само по себе не fault;
- тревожная корреляция: `I↑ + T ускоряется` и/или U перестаёт удерживаться.

### CC

- ток специально удерживается регулятором и не является независимым finish signal;
- фиксируется `Vmax`;
- кандидат финиша — подтверждённый спад `ΔV` от Vmax;
- текущий threshold: 0.03 V;
- тревожная корреляция: `U↓ + T ускоряется`.

### Sticky finish hold

После подтверждённого mode-specific delta V2 запускает обязательный 2 h finish-hold. Небольшие обратные колебания через threshold не отменяют уже подтверждённое событие.

Профильные 10/20 h — fallback-окно поиска evidence. Они не обрывают уже активный 2 h hold. Настоящие safety events имеют приоритет над hold.

## Desulfation

Desulfation — сервисный recovery stage, не финиш и не автоматическая реакция на любое «долго».

Он разрешается только при Recovery/Conditioning и достаточно стабильной умеренной CV-полке. Количество итераций ограничено; после исчерпания бюджета дальнейший transition всё равно проходит через V2 authority.

## SAFE_WAIT / relaxation

После HV штатный путь идёт через output-OFF SAFE_WAIT.

Смотрятся:

- U relaxation;
- dU/dt;
- T stability;
- ток около нуля;
- окна 5m / 10m / 15m, далее longitudinal evidence может хранить 1h / 12h / 24h.

Быстрый спад U — диагностический evidence, но сам по себе не доказательство КЗ банки или стратификации.

## Physical battery registry

V2 умеет работать с сохранённой физической АКБ:

- chemistry, nominal Ah, manufacturer/model;
- condition;
- refill/water history;
- cycles since refill;
- measured capacity, CCA, Ri;
- recovery-cycle evidence и traces.

Для rehydrated AGM ранние циклы сравниваются прежде всего с последующими циклами этой же АКБ, а не с одним универсальным табличным числом.

## Non-bypassable output safety

Любой новый V2 запуск идёт через `HassClient.safe_enable_output()` / `SafeOutputCoordinator`:

1. fresh required telemetry;
2. recipe + absolute envelope validation;
3. OVP;
4. OCP;
5. V;
6. I;
7. readback;
8. повторный preflight;
9. Output ON;
10. post-enable verification;
11. force OFF при любой ошибке.

Telegram success показывается только после подтверждённого `enabled=True`. Ошибка programming/readback/enable откатывает controller session и оставляет output OFF.

## Temperature / hardware safety

Legacy hard safety сохраняется независимо от recipe:

- global current ceiling 12 A;
- battery warning/pause/critical thresholds;
- OVP/OCP;
- watchdog / fast high-voltage watchdog;
- HA communication loss handling;
- `temp_int` защищает БП/контроллер, а не диагностирует АКБ.

## Для ассистента и UI

- Не называй ток «минимальным», если analyzer не сформировал Imin/evidence.
- В CV говори про `Imin -> ΔI`; в CC — про `Vmax -> ΔV`.
- Не путай остаток fallback-window с ETA полного заряда.
- Не утверждай, что 16.3/16.5 V сами по себе являются fault: контекст intent/condition/U-I-T важнее одной цифры.
- Не разрешай Normal/Diagnostic автоматически уходить в HV.
- AI объясняет evidence, но не выбирает и не исполняет hardware setpoints.
