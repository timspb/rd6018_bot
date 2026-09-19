# RD6018 START Orchestration Model — WORKSTREAM 86

Статус: `START_ORCHESTRATION_READY`

## Назначение

`StartOrchestrator` связывает V3-контракты в dry-run потоке. Он не подключён к
production, V2 START path, node 101 или физическому executor.

```text
StartRequest
    |
    v
StartAuthority
    |
    v
StartIdentity + SessionStarted
    |
    v
ExecutionIntent
    |
    +--> safety gate
    |
    +--> approval gate
    |
    v
dry-run stop before PhysicalExecutionRequest
```

## Семантика

- `ALLOW` создаёт identity и lifecycle event, затем формирует data-only
  `ExecutionIntent`.
- `DENY`/`AMBIGUOUS` не создают identity, lifecycle event или intent.
- Отсутствующие targets, safety deny и approval failure возвращаются через
  `blocked_reason`; созданные ранее контракты не исполняются.
- Успешный dry-run не создаёт и не отправляет `PhysicalExecutionRequest`.
  `physical_request_created` всегда остаётся `False`.

## Границы безопасности

Модуль не импортирует V2, HA, ESPHome, RD, Modbus и transport adapters. Он
создаёт только immutable data contracts и вызывает только инъецированные
read-only gate functions. Lifecycle `SessionStarted` не означает, что
физический Output включён; это подтверждается отдельным execution/readback
контрактом в будущем.
