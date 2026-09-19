# RD6018 STOP / PAUSE / EMERGENCY Ownership Model — WORKSTREAM 88

Статус: `CONTROL_OWNERSHIP_DESIGN_READY`

Это read-only audit и boundary design. Runtime, production и physical
ownership не изменяются.

## 1. Фактические V2 пути

### STOP

Основной manual path:

```text
Telegram/operator stop
    -> ProductionManualSessionManager.stop(reason)
    -> HassClient.turn_off()
    -> output readback
    -> ManualSessionState.STOPPED или FAILED
    -> persistence
    -> SESSION_STOPPED canonical event, если identity уже есть
```

Для controller/runtime path `runtime.v2_runtime._hard_stop_charge()` вызывает
`charge_controller.stop(...)`, очищает pause state и использует существующий
SafeOutput/HA boundary. Владелец физического OFF остаётся V2 safety/output
boundary; V3 не получает его.

### PAUSE

V2 operator pause хранится отдельно в `operator_pause_state.json` через
`operator_pause_started_at`. При включении pause output переводится OFF и
проверяется readback; сессия сохраняется, но это не terminal STOP. При resume
проверяются OVP/OCP, температура, входное напряжение и восстановление сессии,
после чего применяется guarded enable. Pause/resume не являются V3 physical
commands и не должны дублироваться новым V3 UI.

Manual thermal cooling также использует состояния `COOLING -> ARMING -> ACTIVE`
и отдельный `safe_enable_output`; это автоматическая safety/pause semantics,
не операторский STOP.

### EMERGENCY

Emergency/containment запускается V2 safety/runtime paths: watchdog, потеря
телеметрии/связи, safety diagnostics, lease/dead-man и explicit emergency stop.
Канонический физический результат — guarded/verified Output OFF через
существующий SafeOutput/edge boundary. Audit evidence фиксирует reason,
timestamp и readback; отсутствие подтверждения OFF остаётся failure/unknown,
а не успешным STOP.

## 2. Текущая ownership matrix

| Действие | Lifecycle/session writer | Physical writer | V3 status |
|---|---|---|---|
| STOP | V2 controller/manual manager | V2 SafeOutput/HA boundary | observe/design |
| PAUSE | V2 runtime pause state + session persistence | V2 guarded OFF/enable | observe/design |
| EMERGENCY | V2 safety/runtime + edge lease | V2 safety/edge boundary | observe/design |

Identity (`session_id`, `trace_id`) сохраняется только если текущая session
имеет identity; legacy session без identity должна показываться как UNKNOWN или
AMBIGUOUS, без synthetic event.

## 3. Будущий canonical boundary

```text
StopAuthority
    -> StopRequested lifecycle event
    -> ExecutionIntent(OUTPUT_OFF)
    -> safety/approval
    -> existing physical owner during bridge

PauseAuthority
    -> PauseRequested / PauseConfirmed lifecycle events
    -> preserve session identity and lifecycle snapshot
    -> physical OFF/enable remains separate execution result

EmergencyAuthority
    -> EmergencyDetected / ContainmentRequested audit events
    -> safety decision
    -> one containment execution boundary
    -> verified readback / explicit UNKNOWN
```

Единый owner принимает semantic decision. Физический owner до отдельного
cutover остаётся V2. Lifecycle event не подменяет physical confirmation:

- request event — до physical action;
- confirmed/stopped event — только после required readback;
- failed/unknown event — при отсутствии подтверждения.

## 4. Защита от двойных действий

Для каждого control request нужен immutable `request_id`, `session_id` и
`trace_id`. Повтор того же request должен быть idempotent. Одновременные V2/V3
STOP/PAUSE/EMERGENCY requests проходят conflict guard; V3 shadow observer не
вызывает V2 handler и не создаёт physical request.

## 5. Rollback и recovery

- STOP: V2 остаётся rollback owner; не возобновлять старую session без fresh
  verification.
- PAUSE: сохранять lifecycle snapshot и identity; resume разрешать только после
  свежей safety/readback проверки.
- EMERGENCY: не восстанавливать output автоматически; lease/containment остаётся
  консервативным до подтверждённого recovery и явной authority процедуры.

## 6. Запреты до внедрения

- не менять V2 handlers или state machine;
- не создавать `StopAuthority`, `PauseAuthority` или `EmergencyAuthority` в
  production composition;
- не подключать executor/HA/ESPHome/RD;
- не выполнять реальные STOP, PAUSE, RESUME или EMERGENCY commands.

