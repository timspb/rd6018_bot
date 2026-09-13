# V3 Phase 7F — decision ownership

Статус: inventory and intent schema review

Baseline: `0e24b97ad3e88e0f8366bdb6f4d9123524f930c6`

## ChargeIntent completeness

Текущий `ChargeIntent` уже содержит все требуемые domain-level поля:

| Required concept | ChargeIntent field |
|---|---|
| target voltage | `target_voltage` |
| target current | `target_current` |
| stage | `next_stage` — stage requested after evaluation |
| completion | `completed` |
| reason | `reason` |

Дополнительные поля не требуются для текущей boundary. `ChargeIntent` остаётся
immutable data-only result и не получает HA/RD/Telegram/lease/safety objects.

## Decision ownership inventory

| Decision | Current owner | Readers | Future V3 owner | Migration blocker |
|---|---|---|---|---|
| target voltage | `ChargeController`/V2 action decisions and program-specific config | action executor, UI, persistence | `ChargeProgram` → `ChargeIntent`, validated by `SafetyEngine` | legacy/V2 writers coexist |
| target current | `ChargeController`/V2 action decisions and Manual manager | action executor, UI, persistence | `ChargeProgram` → `ChargeIntent`, bounded by `SafetyEngine` | legacy/V2 writers coexist |
| stage | legacy `ChargeController` plus V2 subclasses | tick, restore, UI, evidence | single `ChargeState` + `ChargeEngine` | scaffold inheritance and restore callers |
| completion | V2/legacy transition logic plus Manual lifecycle | restore, UI, persistence | `ChargeProgram` result recorded in `ChargeState` | multiple completion/stop paths |
| program transitions | V2 authority/production controller and legacy FSM | controller tick, evidence, UI | `ChargeProgram`/`ChargeEngine` only | full parity for every program |
| enable/disable intent | controller action dict, Manual manager, explicit ownership transactions | safety wrappers, HA adapter, UI | domain emits intent only; `SafetyEngine` decides physical action | direct legacy action executor |
| safety limits | `SafetyEngine`/runtime safety wrappers and edge lease boundaries | all actuator paths | `SafetyEngine` remains sole authority | ordered monkey wrappers and physical gate |

## Current vs future boundary

```text
Current V2/legacy decision writers
        ↓
ChargeStateProvider (read-only snapshot)
        ↓
ChargeEngine / ChargeProgram
        ↓
ChargeIntent (domain only)
        ↓
future SafetyEngine → OutputAdapter → RD
```

`ChargeProgram` may decide target/stage/completion intent, но не может включать
или выключать Output, изменять lease, писать HA или обходить safety limits.
`enable/disable intent` therefore is not an actuator permission; it is data for a
future safety-mediated boundary.

## Migration blockers

- убрать двойную запись stage/targets/timers/completion из legacy/V2 scaffold;
- определить один restore decision owner после authority resolution;
- доказать parity program transitions по representative/full corpus;
- оставить safety/lease/ownership above all intents;
- сохранить production output semantics до physical validation.

Любое расхождение в intent или safety behavior блокирует перенос соответствующей
decision boundary. Production runtime, controller/FSM, UI, Output, ESPHome/YAML
и node 101 не изменялись.
