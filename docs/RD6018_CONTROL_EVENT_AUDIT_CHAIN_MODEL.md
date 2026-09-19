# RD6018 Control Event Audit Chain — WORKSTREAM 89

Статус: `CONTROL_EVENT_AUDIT_CHAIN_READY`

Это design-only модель. Она не подключает physical executor и не изменяет V2,
production, node 101 или существующий control path.

## 1. Единый envelope

Каждый control/audit event должен использовать общий immutable envelope:

```text
event_id       уникальный event identity
event_type     START / STOP / PAUSE / EMERGENCY / verification / recovery
session_id     identity зарядной сессии
trace_id       identity всей операции
decision_id    identity semantic decision
intent_id      optional control intent identity
timestamp      monotonic event time
actor/source   кто обнаружил или создал событие
result         фактический результат
reason         объяснение
```

`event_id` защищает от дублей, а связка `session_id + trace_id + decision_id`
обеспечивает корреляцию. `timestamp` должен быть неубывающим внутри одного
trace. Отсутствующий identity не восстанавливается догадкой: ветка получает
`UNKNOWN`/`AMBIGUOUS`.

Текущий `DecisionAuditEvent` уже покрывает event/decision/session identity,
ordering, replay и duplicate event protection. Для полного control chain его
следующая версия должна явно добавить `trace_id` и `event_type`, не ломая
совместимость существующих decision steps.

## 2. Canonical chains

### START

```text
StartIntent
 -> StartDecision
 -> SessionStarted
 -> ExecutionIntent / request observation
 -> PhysicalVerification
```

`SessionStarted` фиксирует lifecycle identity, но не означает Output ON.
`PhysicalVerification` добавляется только фактическим verification boundary.

### STOP

```text
StopIntent
 -> StopDecision
 -> StopRequested
 -> physical OFF observation
 -> SessionStopped / STOP_FAILED
```

`SessionStopped` допустим только после требуемой physical confirmation; при
неподтверждённом OFF результат должен быть `FAILED` или `UNKNOWN`.

### PAUSE

```text
PauseIntent
 -> PauseDecision
 -> PauseRequested
 -> lifecycle snapshot preserved
 -> Output OFF observation
 -> PauseConfirmed
 -> ResumeRequested / ResumeDecision
 -> continuity preserved
```

Pause не превращается автоматически в terminal STOP. Session identity,
phase/lifecycle snapshot и pause interval сохраняются; resume требует свежей
safety/readback проверки.

### EMERGENCY

```text
SafetyTrigger
 -> EmergencyDetected
 -> ContainmentRequested
 -> physical action observation
 -> EmergencyVerification
 -> RecoveryState
```

Emergency evidence не утверждает успешный physical result без readback. При
потере подтверждения сохраняется fail-closed `UNKNOWN`/containment state.

## 3. Ordering and replay

Audit store остаётся append-only: `append` возвращает новый trail, не меняя
старый. Валидатор обязан отклонять:

- повторный `event_id`;
- смешение session/trace/decision identities;
- timestamp, идущий назад;
- событие без обязательной identity;
- replay с отсутствующей обязательной причинной ступенью.

Replay возвращает фактический порядок, missing events и причины. Отсутствующие
события не реконструируются задним числом.

## 4. Duplicate protection and rollback

Для каждого intent используется idempotency key, связанный с `intent_id`.
Повторный delivery возвращает прежний audit result. Concurrent V2/V3 control
requests блокируются ownership/conflict guard; shadow V3 не отправляет control.

Rollback owner до отдельного cutover — V2. Rollback сохраняет audit trail,
отзывает pending authority/approval и не добавляет fake lifecycle event.

## 5. Boundary rules

- Audit trail наблюдает и объясняет, но не выполняет commands.
- Physical action и verification записываются как observations от физического
  owner, а не синтезируются audit layer.
- START/STOP/PAUSE/EMERGENCY authority остаются design concepts до отдельного
  внедрения.
- Node 101, HA, ESPHome, RD, lease и production composition не подключаются.

