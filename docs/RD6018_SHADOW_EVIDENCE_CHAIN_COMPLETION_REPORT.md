# RD6018 Shadow Evidence Chain Completion — WORKSTREAM 20

## Итог

**BLOCKED** — complete fresh V3 shadow evidence chain не подтверждена.

V2 остаётся production/decision/execution/physical owner. V3 использует только supplied evidence и replay; Canary, authority transfer, lease takeover и physical commands не выполнялись.

## Required chain

Минимальная цепочка:

`SessionStarted → PhaseStarted → PhaseTransition → DeltaStarted → DeltaCompleted → HoldStarted → HoldCompleted → TerminationDetected → SessionStopped`

Каждое событие должно иметь timestamp, session_id, trace_id, source и telemetry correlation (`telemetry_ref`).

## Available evidence

Ранее собранная HA-only observation подтверждает свежие измерения, output/readback snapshots и часть persisted/journal state. Она не содержит полной V3 canonical event chain и не имеет V3 trace/session correlation для всей сессии. Прямое ESPHome observation также не было выполнено.

## Replay validation

`ShadowReplayEngine` и validator реализованы и протестированы на synthetic complete chain. Synthetic chain используется только для contract tests и не считается live evidence. На доступном live package replay не может доказать profile/phase/strategy/session lifecycle полностью, поэтому status остаётся BLOCKED.

## Gaps

| Gap | Category | Source/owner | Resolution |
|---|---|---|---|
| Missing V3 canonical events | MISSING_EVENT | V2 journal/history; V3 observability | bounded read-only observation with event normalization |
| No complete telemetry correlation | MISSING_SOURCE | telemetry collector | attach telemetry_ref to every event |
| Direct ESPHome source absent | MISSING_SOURCE | external integration owner | collect read-only ESP source evidence |
| Current chain not replay-complete | UNKNOWN | V3 observability | obtain START-to-STOP evidence, then replay |

## UI validation

Session timeline contract resets graph samples when a new session starts; this is covered by tests. Live UI validation cannot be claimed until a complete session evidence bundle exists. No stale history should be accepted as the current session.

## Blocker status

`CB-EVIDENCE-001` remains OPEN. It is not resolved by synthetic tests or by HA telemetry alone. Required next step is a V2-owned, bounded, read-only observation window that captures the complete chain and correlates telemetry/diagnostics. No control action is needed or permitted for this evidence collection.
