# Charge Strategy Reference

Этот документ — короткий source of truth по текущей production-стратегии V2.

Перед изменением FSM/evidence сначала сверяться с:

1. `V2_DECISION_LOG.md` — принятые решения;
2. `V2_OPEN_QUESTIONS.md` — то, что ещё **не** решено;
3. этим документом;
4. `PB_RECOVERY_V2.md`;
5. `V1_BEHAVIORAL_AUDIT.md` — фактическое поведение V1.

Полная иерархия описана в `docs/assistant/README.md`.

## Главная модель

В V2 независимы:

- **chemistry**: AGM / EFB / Ca/Ca / Flooded / Custom;
- **intent**: Normal / Recovery / Conditioning / Diagnostic;
- **condition**: Unknown / Healthy / Sulfated suspected / Dry suspected / Rehydrated / Overwet suspected / Stratified suspected / Degraded;
- **stage/mode**: Prep / Main / Desulfation / Mix / SAFE_WAIT / Cooling / Done; Manual проектируется как отдельный явный режим.

`AGM + NORMAL` и `AGM + REHYDRATED + RECOVERY` — разные controller contexts.

## Production authority

- `ProductionChargeControllerV2` — live controller.
- `ChargeControllerV2` владеет Main/Mix decisions для non-Custom V2 paths.
- Legacy `ChargeController.tick()` пока используется как scaffold для зрелых общих механизмов: базовая telemetry validation, temperature safety, SAFE_WAIT, restore/persistence и совместимые safety mechanics.
- Legacy Main/Mix transition triggers маскируются там, где authority принадлежит V2.
- `V2_AUTHORITATIVE=0` — аварийный rollback actuator-логики.
- `V2_UI=0` — rollback нового Telegram UI без автоматического снятия hardware safety.

## Сигналы и термины

### Напряжение

- `battery_voltage` — батарейное напряжение для chemistry decisions;
- RD output voltage — фактическое выходное напряжение источника и hardware-watchdog сигнал.

Это разные сущности.

### Температура

- `temp_ext` — температура АКБ, источник chemistry temperature compensation и battery thermal decisions;
- `temp_int` — температура RD6018/БП, только hardware protection/PSU health.

### Vin

`input_voltage`/Vin — мониторинг здоровья входного БП. Он **не** является Pb-FSM authority и не должен блокировать/разрешать chemistry transition сам по себе.

### CV / CC

- CV: U controlled, I response -> `Imin -> ΔI`;
- CC: I controlled, U response -> `Vmax -> ΔV`.

Не использовать `!CV` как production-доказательство CC при наличии явного `is_cc`.

## Аппаратная граница

В V2 различаются:

1. commanded setpoint;
2. configured/readback setpoint;
3. measured physical value.

Output enable должен проходить через fail-closed transaction:

1. fresh required charge/safety telemetry;
2. recipe + absolute envelope validation;
3. OVP;
4. OCP;
5. voltage;
6. current;
7. readback V/I/OVP/OCP;
8. повторная проверка;
9. Output ON;
10. post-enable Output/protection/temperature/readback verification;
11. force OFF при любой ошибке.

Абсолютный software voltage ceiling V2: **17.5 V**. Это внешний envelope, а не стандартная recovery-уставка.

`BAT_MODE` наблюдается, но не является разрешением на запуск.

## Базовые targets

Глобальный stage-current ceiling: **12 A**.

### PREP

- ~12.0 V + temperature compensation;
- ~0.01 C;
- смысл: при `Vbat < ~12 V` ток должен оставаться маленьким.

Вопрос о прямом атомарном старте в Main при `Vbat >=12 V` ещё открыт; не воспроизводить V1 logical/physical mismatch как обязательный контракт.

### Main

- ~0.1 C, max 12 A;
- Ca/Ca: 14.7 V base;
- EFB: 14.8 V base;
- AGM: 14.4 -> 14.6 -> 14.8 -> 15.0 V.

### Intermediate recovery / Desulfation

- 16.3 V base;
- ~0.02 C;
- 2 h service attempt;
- это промежуточная recovery-попытка внутри Main/recovery loop, а не final Mix.

### Mix

- Ca/Ca: 16.5 V base;
- EFB: 16.5 V base;
- AGM: 16.3 V base;
- ~0.03 C, max 12 A.

### Done / Storage

Нормальный `Done` означает managed float/storage:

```text
13.8 V / 1.0 A / Output ON
```

Hard stop/fault — отдельная OFF-семантика; не путать с Done.

## Temperature compensation

Legacy formula сохраняется как базовая:

```text
V_comp = V_base + k * (25 - temp_ext)
```

- Ca/Ca, EFB: 0.018 V/°C;
- AGM: 0.016 V/°C;
- Custom: 0.018 V/°C;
- legacy correction clamp: примерно ±0.60 V.

После расчёта production V2 обязан применить recipe/absolute envelope.

## Main: normal tail и stuck plateau — разные механизмы

### Normal tail

V1 baseline:

- Ca/Ca/EFB: CV + low-current tail порядка 0.30 A и 3 h без нового минимума;
- AGM: CV + порядка 0.20 A и 2 h, со staged Main voltages.

V2 evidence может нормализовать thresholds относительно capacity/C-rate, но не должен терять смысл “новый минимум = новый отсчёт tail evidence”.

### Stuck plateau

Отдельно детектируется lack of progress:

- Ca/Ca/EFB: исторически ~40 min flat CV plateau;
- AGM: ~2 h, намеренно более консервативно.

Плавное падение тока — это progress, не plateau.

Один C-rate cutoff сам по себе не доказывает fault. Ранее временно введённое правило `>~1%C => automatic HV veto` **отклонено и удалено**. Fault/HV decisions должны учитывать более полное U/I/T и diagnostic evidence.

## Recovery-attempt budget

Для Ca/Ca/EFB принята session-wide модель:

```text
plateau -> recovery #1 -> Main
later plateau -> recovery #2 -> Main
later plateau -> recovery #3 -> Main
next confirmed plateau -> final Mix
```

Progress между попытками не обнуляет count. Счётчик обнуляется только новой charge session.

AGM policy остаётся отдельной и консервативной; финальные детали бюджета AGM перечислены в open questions.

## Main hard timeout

V1 Ca/EFB ~72 h Main -> Mix не считается найденным багом.

Stuck-current recovery срабатывает раньше отдельным механизмом. 72 h — fallback для длительных non-completing trajectories, например очень медленного непрерывного снижения тока.

Как этот fallback должен взаимодействовать с новым `intent` model перед merge — ещё открытый вопрос.

## Mix: mode-specific evidence

После target change действует ~120 s blanking.

### CV

- фиксируется реальный `Imin`;
- finish candidate: подтверждённый рост `ΔI`;
- ориентир threshold: `max(0.03 A, 30% * Imin)`.

### CC

- фиксируется `Vmax`;
- finish candidate: подтверждённый спад `ΔV`;
- ориентир threshold: ~0.03 V.

### Confirmation

- 3 spaced confirmations;
- примерно minute-class spacing;
- одиночный crossing не является finish evidence.

### Sticky finish hold

После подтверждения запускается sticky **2 h** finish hold. Небольшой возврат через threshold не стирает уже подтверждённое событие.

Настоящие safety events имеют приоритет над hold.

### Mix fallback maxima

Принятые V2 maximum observation windows:

| Chemistry | Max Mix fallback |
|---|---:|
| Ca/Ca | 20 h |
| EFB | **24 h** |
| AGM | 10 h |

Это не ETA и не нормальная длительность стадии. Если valid sticky 2 h finish hold уже запущен, crossing fallback boundary сам по себе его не отменяет.

## SAFE_WAIT

После HV Output выключается и начинается relaxation bridge.

Contract:

```text
threshold reached early -> continue immediately
not reached -> wait max ~2 h -> continue to lower-energy target anyway
```

2 h — anti-stall maximum, не fault timeout.

Slow/fast relaxation остаётся diagnostic evidence.

## Cooling

Cooling — **pause chemistry time**, не новая батарейная evidence-stage.

Принятые semantics:

- Output OFF;
- source stage/target preserved;
- stage elapsed clock paused;
- recovery budget preserved;
- established diagnostic extrema preserved;
- continuity-dependent evidence invalidated;
- partial Mix reversal confirmations cleared;
- stuck plateau must be proved again after resume;
- already-confirmed sticky finish hold remains confirmed, but its clock is paused;
- Cooling state is persisted so restart cannot silently re-enable stale pre-Cooling state.

Battery thresholds remain approximately warning/pause/critical = 35/40/45 °C.

`temp_int` hardware precritical remains around 55 °C class.

## Manual mode

Manual operation is a supported product feature, not debug escape hatch.

Target V2 principle:

- explicit MANUAL representation;
- richer operator input;
- global absolute envelope;
- automatic OVP/OCP derivation unless explicitly designed otherwise;
- readback verification;
- battery and PSU thermal safety;
- watchdogs;
- persistent Manual OFF conditions.

Exact schema/restore semantics remain open.

## Manual OFF

Independent operator kill conditions remain supported:

- V>=;
- V<=;
- I>=;
- I<=;
- timer;
- combinations.

They are stop conditions, not chemistry finish evidence. Exact priority versus automatic completion/recovery remains open; hard safety can never be suppressed.

## Battery diagnostics / bank-fault

V1 bank-fault detector is heuristic and advisory. V2 must not call a specific cell fault proven from one V/I observation.

Desired direction:

- separate hypotheses;
- longitudinal evidence per physical battery;
- relaxation behavior;
- capacity/CCA/Ri where available;
- potentially controlled `ΔI -> ΔV` probes;
- per-cell inputs if operator supplies them.

The threshold at which a confirmed diagnostic may block further HV is still open.

## Physical battery registry

V2 can bind evidence to a saved physical battery:

- chemistry and nominal Ah;
- manufacturer/model;
- condition;
- refill/water history;
- cycles since refill;
- measured capacity / CCA / Ri;
- recovery traces and outcomes.

This enables “compare battery with itself” instead of relying only on universal table values.

## Watchdog principle

Preserve the V1 invariant:

```text
higher-energy state -> shorter allowed blind-operation interval
```

High-voltage control/telemetry loss must trip faster than ordinary low-energy monitoring loss.

## AI boundary

AI/LLM remains explanation-only:

```text
deterministic controller owns hardware
AI explains evidence
```

AI does not choose setpoints, authorize HV or override hard safety.

## Operator/documentation rules

- Не называй current “Imin”, пока analyzer действительно не сформировал minimum evidence.
- В CV описывай `Imin -> ΔI`; в CC — `Vmax -> ΔV`.
- Не называй fallback-window ETA полного заряда.
- Не считай SAFE_WAIT timeout fault сам по себе.
- Не считай один высокий ток доказательством cell fault.
- Не путай Done/Storage с Output OFF.
- Не путай Vin/`temp_int` с battery chemistry evidence.
- Если вопрос находится в `V2_OPEN_QUESTIONS.md`, не додумывай решение по памяти.
