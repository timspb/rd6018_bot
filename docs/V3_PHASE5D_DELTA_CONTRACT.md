# V3 Phase 5D — Delta behavior contract

Статус: contract only; `DeltaProgram` не реализован

Baseline: `372fd25318d13ee377b0a39a3e230df9da8dacd8`

## 1. Domain inputs

Будущая pure Delta program получает:

- `Measurements`: свежие voltage/current/temperature/time snapshots;
- `ChargeState`: текущая program/stage/timer context;
- `BatteryProfile`: chemistry, capacity и declared limits;
- Delta configuration: режим CV/CC, reference extreme, accepted delta,
  confirmation policy и sticky hold duration.

Ни один input не даёт программе доступа к HA, RD/ESP, Telegram, persistence,
lease или safety.

## 2. State model

| State | Purpose | Allowed transitions | Intent |
|---|---|---|---|
| `UNARMED` | Delta evidence ещё не начата | `TRACKING` при свежем валидном source | target continuation, `completed=false` |
| `TRACKING` | наблюдение reference и reversal | остаётся `TRACKING`, либо `CONFIRMED_HOLD`, либо `STOPPED` при stale/invalid evidence | target continuation, `completed=false` |
| `CONFIRMED_HOLD` | accepted Delta sticky hold | остаётся hold, либо `COMPLETE`, либо `STOPPED` по safety/stop | target continuation, `completed=false` |
| `COMPLETE` | accepted finish hold завершён | terminal для Delta | следующий stage, `completed=true` |
| `STOPPED` | evidence invalid или остановка | terminal для Delta decision | no target mutation, `completed=true` |

CV uses fresh Imin followed by accepted Delta-I reversal. CC uses fresh Vmax
followed by accepted Delta-V fall. Historical/Recorder values не являются
Delta authority. Exact confirmation spacing and hold timing остаются частью
конфигурации принятого production contract.

## 3. Transition table

| Current state | Condition | Next state | Reason |
|---|---|---|---|
| `UNARMED` | fresh valid source and tracking requested | `TRACKING` | `DELTA_ENTER` |
| `TRACKING` | evidence not confirmed | `TRACKING` | `DELTA_HOLD_WAIT` |
| `TRACKING` | accepted CV Imin→ΔI or CC Vmax→ΔV confirmation | `CONFIRMED_HOLD` | `DELTA_HOLD_START` |
| `TRACKING` | invalid or stale evidence | `STOPPED` | `DELTA_EVIDENCE_INVALID` |
| `CONFIRMED_HOLD` | sticky finish hold elapsed | `COMPLETE` | `DELTA_COMPLETE` |
| `CONFIRMED_HOLD` | hard safety/stop condition | `STOPPED` | `DELTA_STOP` |

Таблица зафиксирована data-only в `runtime/charge/contracts/delta.py`; она не
исполняет transitions.

## 4. Intent mapping

| State/event | target voltage | target current | stage | completion | reason |
|---|---:|---:|---|---|---|
| enter/tracking | current program target | current program target | `delta` | false | `DELTA_ENTER` / wait |
| accepted confirmation | current program target | current program target | `delta` | false | `DELTA_HOLD_START` |
| hold complete | current program target or next policy target | current program target or next policy target | next stage | true | `DELTA_COMPLETE` |
| invalid/stale/stop | none | none | `stopped` | true | stop reason |

Representative vectors фиксируют конкретные values: tracking/hold use `14.4 V`,
`2.0 A`, completion uses `done`, invalid stop has no targets. Это vectors для
проверки контракта, не recipe и не actuator authorization.

## 5. Timing ownership

Algorithm owns:

- Delta calculation from fresh observations;
- CV/CC reference and reversal conditions;
- confirmation transitions;
- sticky hold completion and reason.

Infrastructure owns:

- scheduler/tick cadence;
- telemetry acquisition;
- persistence/restore;
- Output and setpoint writes;
- HA/RD/ESP transport;
- Telegram/UI;
- lease, ownership and safety enforcement.

После confirmed event sticky hold должен быть durable/observable через внешний
state owner, но сама program не записывает persistence.

## 6. Representative vectors and gate

`delta_cases` содержит entry, confirmation-to-hold, hold completion и invalid
evidence stop cases. Contract tests проверяют загрузку vectors и соответствие
каждого vector transition table, а также отсутствие external imports.

До реализации Delta любой mismatch в этих vectors блокирует migration. Нельзя
выводить из этого документа ни Output command, ни lease/safety decision.

DeltaProgram, legacy execution, controller migration, FSM rewrite, production,
ESPHome/YAML и node 101 не изменялись.
