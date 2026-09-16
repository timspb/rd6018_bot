# RD6018 domain logic extraction (Phase 5.1)

Статус: контрактный анализ, без подключения к runtime.

## Граница

В домен V3 разрешено переносить только детерминированные решения по фазам,
уставкам, evidence и переходам. Telegram, HA, ESPHome, физические вызовы,
legacy globals, bootstrap и UI state остаются вне домена.

```text
Measurements + ChargeIntent + BatteryProfile
                    |
                    v
          pure program / strategy
                    |
                    v
              domain decision
```

Решение домена не выполняет intent. Его исполняющий владелец остаётся V2.

## Источник фактов

- V1/V2 legacy domain scaffold: `charge_logic.py` (`ChargeController`).
- V2 composition: production controller and `start_profile_transactional()`.
- Native V3 contracts: `runtime/charge/state.py`, `program.py`, `strategy/`,
  `programs/`, `profiles/`.

## Extracted domain inputs

Обязательные: battery chemistry/profile, capacity, voltage, current, battery
temperature when a temperature rule is active, output state and elapsed time.
Программа также получает explicit intent and validated recipe. Connectivity,
HA health, transport health and lease state are infrastructure context; они не
являются charge-program inputs.

## Extracted decisions

1. Main policy выбирает Main target, tail/plateau evidence и recovery.
2. Minimum policy подтверждает минимальный ток с опциональным напряжением.
3. Delta policy фиксирует observed extremum, требует подтверждения и sticky
   hold.
4. Mix authority ограничивает active time и возвращает terminal decision при
   timeout.
5. Safety envelope валидирует recipe/domain limits; infrastructure safety
   остаётся отдельным слоем.

## V1/V2 parity findings

- V1 charge FSM и persisted session остаются историческим behavioral baseline.
- V2 сохранил V1 transaction/physical owner, но добавил strategy, evidence,
  readback и ownership gates вокруг него.
- V2 текущая production strategy задаёт EFB Mix authority 24 h; старый
  `charge_logic.py` содержит 20 h. Это configuration/contract drift, не
  разрешённый повод менять значение в этой фазе.
- Native V3 CC Delta contract сравнивает падение тока от captured reference,
  тогда как production V2 CC completion описывается как Vmax/Delta-V evidence.
  Это parity blocker до будущего решения, runtime не подключается.

## Classification

### KEEP FROM V1

- explicit phase/state vocabulary and bounded transitions;
- session start/stop/restore semantics as a documented compatibility baseline;
- chemistry-specific envelopes and terminal OFF requirement;
- evidence-before-transition and timed holds.

### KEEP FROM V2

- separated intent, recipe, measurements and strategy contracts;
- Main/Recovery/Mix decomposition;
- confirmed Delta and sticky hold model;
- explicit infrastructure safety boundary and V2 execution ownership;
- shadow comparison before any execution wiring.

### REIMPLEMENT IN V3

- pure profile registry for AGM, EFB, Ca/Ca and explicit Custom;
- complete state transition contract including invalid/stale evidence;
- session lifecycle as data-only domain state;
- domain safety envelope independent of HA/ESPHome;
- parity-approved CC/CV Delta semantics after resolving the blocker.

### DISCARD

- Telegram/UI text and callbacks;
- HA/ESPHome clients and transport retries;
- direct actuator calls and controller/session globals;
- installer/bootstrap behavior and presentation-only state.

## Non-goals

This document does not authorize an executor, START/ACTIVE wiring, recipe value
changes, or migration of the V2 controller owner.
