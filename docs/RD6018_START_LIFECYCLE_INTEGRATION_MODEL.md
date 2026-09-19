# RD6018 START Lifecycle Integration Model — WORKSTREAM 84

Статус: `START_LIFECYCLE_DESIGN_READY`

Документ описывает целевой контракт. Внедрение в V2, production, node 101 и
physical control не выполнялось.

## 1. Current ownership

Сейчас существуют два независимых пути:

```text
V2 UI → charge_controller → HA/RD
       └─ V2 log/checkpoint

ManualSessionManager.start()
       ├─ identity
       ├─ manual_session_v2.json
       ├─ safe_enable_output()
       └─ canonical SESSION_STARTED
```

`v2_bot_ui._start_profile()` может включить физический output через controller
и HA, не вызывая `ProductionManualSessionManager.start()`. Поэтому Output ON
не является canonical lifecycle START.

## 2. Canonical future path

```text
Operator START intent
        |
        v
START Authority / Session Manager
        |
        +-- create session_id and trace_id
        |
        +-- persist candidate identity
        |
        v
SessionStarted / lifecycle START event
        |
        v
Domain decision → Safety decision → ExecutionIntent
        |
        v
Approval / execution boundary
        |
        v
Physical executor
        |
        v
Readback verification → lifecycle confirmation
```

Ключевое правило: lifecycle START — это принятие operator intent и создание
session identity, а не пост-фактум наблюдение физического Output ON.

## 3. Authority allocation

### START authority

Единственным владельцем START должен быть application-level
`StartAuthority`/`SessionManager`. UI только создаёт `OperatorIntent`; он не
вызывает controller или transport.

### Session identity

`session_id` создаётся ровно один раз при принятии нового START intent.
`trace_id` создаётся в том же boundary для всей цепочки decision/execution.
Оба идентификатора должны существовать до `SessionStarted` и передаваться
неизменно во все последующие events, telemetry correlation, audit и evidence.

### Execution confirmation

Execution boundary подтверждает только физический результат:

- request accepted;
- command applied;
- readback observed;
- verification passed/failed.

Он не создаёт session identity и не объявляет lifecycle START.

### Lifecycle confirmation

Session/lifecycle owner сопоставляет verified execution result с исходным
intent. Только этот owner может перевести session в active lifecycle state и
создать соответствующее lifecycle event. Не допускается считать HA Output ON
самостоятельным `SessionStarted`.

## 4. Required contracts

`StartIntent` должен содержать operator source, program/profile, requested
targets, correlation metadata и timestamp. `SessionIdentityBoundary` выдаёт
immutable `session_id`/`trace_id`. `SessionStarted` ссылается на intent и
identity. `ExecutionIntent` ссылается на decision, но не создаёт identity.

При отказе safety, approval, transport или verification создаётся failure/audit
result; успешный START event задним числом не создаётся.

## 5. Forbidden shortcuts

- не создавать fake `SessionStarted` после наблюдения Output ON;
- не назначать identity пост-фактум активной legacy session;
- не оборачивать старый UI path так, чтобы он сохранял два owner-а;
- не считать `manual_session_v2.json` и V2 controller единым lifecycle owner;
- не давать physical adapter право менять FSM/session state.

## 6. Migration boundary

До отдельного внедрения V2 остаётся production owner. V2 path используется как
behavior reference. Любое внедрение должно сначала доказать parity и иметь
rollback к прежнему owner; этот документ сам ownership не меняет.
