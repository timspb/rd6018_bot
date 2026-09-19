# RD6018 Live Charge Cycle Evidence — WORKSTREAM 22

## Итог

**BLOCKED** — полной реальной V3 shadow chain не получено. V2 остался единственным production/decision/execution/physical owner; START/STOP, actuator writes и lease operations не выполнялись.

## Live session detection

Read-only `/root/rd6018_bot/manual_session_v2.json` на 101:

- state: `active`;
- battery/profile: `Baic72`;
- current stage: `mix`;
- configured: `17.5 V / 3.5 A`;
- started: `2026-09-15T06:07:21Z`;
- saved: `2026-09-15T06:10:39Z`;
- session_id: отсутствует в persisted record.

Это позволяет определить active/profile/phase, но не даёт V3 session identity.

## Live source snapshot

В read-only snapshot `2026-09-15T07:40:14Z` HA и ESPHome согласовали основные значения:

- output ON;
- `17.14 V`, `3.48 A`, `~59.81 W`;
- setpoints/readback `17.5 V / 3.5 A`;
- battery `17.13 V`;
- internal/external temperature `41/35 °C`;
- CC mode, protection `0`;
- lease armed, not tripped, TTL `900 s`, remaining `~652 s`, Modbus age `~5.3 s`.

Source correlation для измерений: **MATCH**. Это telemetry/readback evidence, не evidence полного lifecycle.

## Timeline capture

Требуемая цепочка:

`START → PhaseStarted → PhaseTransition → DeltaStarted → DeltaCompleted → HoldStarted → HoldCompleted → TerminationDetected → SessionStopped`

В текущих источниках отсутствует полная canonical chain. `charging_history.log` содержит исторические/дублирующиеся `SESSION_START` и `SESSION_RESTORE`, а последний видимый fault-маркер — `EMERGENCY_UNAVAILABLE`; подтверждённых Delta/Hold/Termination/STOP событий с общими `trace_id`, `session_id` и telemetry references нет.

## Replay

`LiveChargeCycleObserver` и replay path реализованы. Synthetic full-chain replay проходит только в contract tests. Реальный пакет нельзя считать replay-complete, потому что persisted session не содержит session_id, а canonical event chain не собрана.

## UI validation

Session-scoped graph reset и изоляция timeline покрыты тестом. Для текущей реальной сессии live UI validation Delta/Hold невозможна: соответствующие canonical events отсутствуют.

## Missing events / divergences

| Gap | Classification | Source/owner | Resolution |
|---|---|---|---|
| session_id отсутствует в persisted session | MISSING_SOURCE | V2 session owner | получить correlation ID из live journal/runtime evidence |
| PhaseStarted/PhaseTransition для текущей сессии | MISSING_EVENT | V2 journal/runtime | read-only capture текущего цикла |
| DeltaStarted/Completed | MISSING_EVENT | V2 strategy/runtime | read-only capture strategy events |
| HoldStarted/Completed | MISSING_EVENT | V2 strategy/runtime | read-only capture hold events |
| TerminationDetected/SessionStopped | MISSING_EVENT | V2 runtime/history | дождаться естественного цикла; не инициировать STOP |
| duplicate historical SESSION_START/RESTORE | TIMELINE_CONFLICT | charging_history.log | filter by session/trace, не считать текущим lifecycle |

## Decision

`CB-EVIDENCE-001` остаётся **OPEN/BLOCKED**. Закрытие требует одной естественно завершённой V2-owned сессии, где V3 observer получит полную цепочку и корреляцию; запускать или останавливать заряд для получения evidence запрещено.
## WORKSTREAM 23 update — session identity/correlation

Добавлены observer-only `SessionIdentityModel`, `EventCorrelationResolver`, historical filtering и `CurrentSessionTimeline` contract. Persisted live session по-прежнему не содержит `session_id`, поэтому это исправляет модель корреляции, но не создаёт задним числом отсутствующую live identity. `CB-EVIDENCE-001` остаётся OPEN до естественного complete capture.
## WORKSTREAM 24 update — session birth

Observer contract готов, но новая idle-to-active граница не наблюдалась: live snapshot уже был active/MIX, а persisted record не содержит session_id. `CB-EVIDENCE-001` остаётся OPEN/BLOCKED.
