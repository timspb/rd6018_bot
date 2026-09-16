# V3 Phase 7D — ChargeState ownership

Статус: read-only state provider and inventory

Baseline: `b83ed36d21810fee9d010b7fb316366f50c0d5b9`

## Provider boundary

`ChargeStateProvider` формирует новый `ChargeState` из явно переданных runtime
данных. Он копирует `targets` и `timers`, сохраняет переданный measurements
snapshot reference и ничего не записывает обратно в источник. Provider не имеет
HA/RD/Telegram/Output/lease доступа.

```text
current runtime data
        ↓
ChargeStateProvider
        ↓
ChargeState
        ↓
ChargeService → ChargeEngine
```

`RuntimeApp` владеет provider reference. Production controller пока остаётся
исполняющим владельцем физического runtime state.

## State write inventory

| Field | Current writer | Current reader | Future owner | Migration step |
|---|---|---|---|---|
| mode | `bot_legacy` globals, Manual/ownership managers | handlers, controller, guards | `ChargeState` + `OwnershipManager` | separate ownership/state split |
| stage | `charge_logic.ChargeController`, V2 subclasses | tick, restore, UI | `ChargeState` | snapshot parity then controller boundary |
| voltage target | controller fields/action decisions, legacy tick | action executor, UI, persistence | `ChargeState.targets` | read-only target adapter |
| current target | controller fields/action decisions, legacy tick | action executor, UI, persistence | `ChargeState.targets` | read-only target adapter |
| timers | controller/V2 fields, Manual manager | controller, restore, UI | `ChargeState.timers` | timer snapshot/parity tests |
| completion | controller stop/transition decisions, Manual state | restore, UI, session persistence | `ChargeState.completed` | completion contract vectors |
| battery profile | V2 UI/registry and controller fields | controller/program selection/UI | `BatteryProfile` | domain identity adapter |
| active program | controller/session reason and Manual manager | service/UI/restore | `ChargeState.program` | program selection adapter |

## Double ownership findings

Current stage/targets/timers/completion действительно записываются несколькими
слоями: legacy controller, V2 subclasses/scaffold и отдельный Manual manager.
Это зафиксированный migration blocker, а не разрешение менять behavior. Provider
не скрывает этот split: он создаёт snapshot из выбранного источника, но не
становится writer-ом текущего runtime state.

Battery profile и active program уже имеют domain representations, однако их
production source остаётся распределённым между registry/UI/controller/session.

## Ownership rules

- Provider только формирует snapshot.
- `ChargeState` — будущий единый data owner charge state, не actuator owner.
- `ChargeService`/`ChargeEngine` только читают state и возвращают intent.
- Safety/ownership/Output boundaries остаются внешними.
- Ни один state snapshot не может сам разрешить Output, lease или restore.

## Migration gate

Следующий шаг — read-only adapter текущего controller state с parity checks.
Только после доказательства единственного write path можно переносить mutation
ownership. Любое расхождение stage/timer/completion или изменение actuator path
блокирует миграцию.

Production controller, FSM, UI, Output, safety, ESPHome/YAML и node 101 не
изменялись.
