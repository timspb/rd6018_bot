# RD6018 DiagnosticsDomain boundary — Phase 6.5

## Назначение

`application.diagnostics_domain` — pure contract для фактов наблюдения,
трассировки и operator diagnostics. Он не является charge engine, safety
engine, transport client или UI presenter.

## Event taxonomy

| Category | Examples | Authority |
|---|---|---|
| Domain | phase changed, strategy decision, containment requested, session state changed | Domain/application producer; diagnostics только фиксирует факт |
| Infrastructure | HA unavailable, ESP unavailable, transport timeout, persistence failure | Infrastructure adapter producer |
| Operator | operator action, diagnostic request, notification/audit acknowledgement | UI/application boundary producer |

Infrastructure event сообщает о проблеме транспорта, но не решает, нужно ли
останавливать заряд. `containment requested` фиксирует уже принятое внешним
owner решение, но DiagnosticsDomain его не создаёт и не исполняет.

## Contracts

`TraceCorrelation` содержит `trace_id`, `span_id`, optional parent span и
session identity. `DiagnosticEvent` неизменяем и содержит event id, timestamp,
category, type, severity, source, correlation и plain payload. Optional fields
`error_code`, `warning_code` и `audit_action` позволяют нормализовать ошибки,
предупреждения и audit records без отдельного writer.

`DiagnosticsDomain.event()` только создаёт immutable record. В Phase 6.5 нет
production sink, journal writer, Telegram sender, dashboard adapter или
persistence hook.

## Forbidden dependencies

DiagnosticsDomain не импортирует и не вызывает:

- ChargeEngine, StrategyEngine или SafetySupervisor;
- controller, FSM или session mutators;
- HA, ESPHome, RD transport или lease;
- SafeOutputCoordinator, actuator и physical layer;
- Telegram/dashboard/persistence writers.

Operator presentation остаётся отдельным consumer layer: Telegram, dashboard и
notifications могут форматировать события, но не становятся владельцами
diagnostic records или runtime decisions.

## Rollout boundary

Контракт добавлен без production wiring. START, ACTIVE, safety behavior,
transport, persistence и physical execution не изменены.
