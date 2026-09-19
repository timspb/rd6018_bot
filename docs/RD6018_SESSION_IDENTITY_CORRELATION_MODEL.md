# RD6018 Session Identity & Event Correlation Model — WORKSTREAM 23

## Граница ответственности

Модель является observer/correlation layer. Она не изменяет V2 session/FSM, START/ACTIVE, physical execution, lease или HA/ESP control.

## SessionIdentityModel

Identity создаётся аналитически для `START`, restored active session и resumed session. Поля: `session_id`, `created_at`, `source`, `profile`, `initial_phase`; flags `restored` и `resumed` различают происхождение без записи в старый runtime state.

## EventCorrelationResolver

Сопоставляет supplied journal/history/persisted/telemetry/diagnostics events по session identity, timestamp range, phase и trace/source metadata. При cross-session событии в текущем временном диапазоне возвращается `AMBIGUOUS`; система не угадывает принадлежность.

## Historical filtering

Events до identity creation или с другим session ID помещаются в `HISTORICAL`, если конфликт не попадает в текущий временной диапазон. Current events проходят только при согласованных identity/time/phase. Старые `SESSION_START` и `RESTORE` не попадают в current timeline.

## TimelineReconstructionResult

Reconstructor выдаёт `COMPLETE`, `PARTIAL` или `AMBIGUOUS` для цепочки `START → phases → Delta → Hold → termination → STOP`. Ambiguous result запрещён для выдачи как current UI timeline.

## UI contract

`CurrentSessionTimelineProvider` принимает только reconstruction result, возвращает timeline с одним `session_id`, `graph_reset=True` и `historical_events_included=False`. Raw history в UI не передаётся.

## Live status

Контракты и тесты готовы: `SESSION_CORRELATION_READY`. Это не закрывает автоматически `CB-EVIDENCE-001`: для закрытия нужен реальный complete chain capture с session/trace IDs.
