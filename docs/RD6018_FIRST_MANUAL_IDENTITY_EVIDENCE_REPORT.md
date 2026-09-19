# RD6018 First Manual Identity Evidence Capture — WORKSTREAM 29

## Status

**`BLOCKED`** — `MANUAL_IDENTITY_EVIDENCE_CAPTURED` не подтверждён.

## Observation result

В текущем observation window новая V2-owned Manual сессия не наблюдалась:

- новый `SessionStarted` не получен;
- новая `session_id/trace_id` пара не получена;
- полный START-to-STOP цикл отсутствует;
- старая `Baic72` сессия и synthetic events не использовались для закрытия blocker.

Локальный workspace не содержит live `manual_session_v2.json`; identity integration
проверена контрактными тестами, но это не является live evidence.

## Prepared evidence path

`ManualIdentityEvidenceCollector` принимает только внешне собранные V2-owned
events/telemetry/readback/ESP/HA/diagnostics, проверяет полную цепочку и запускает
replay-only. При неполной цепочке результат `PARTIAL`, при отсутствии identity или
events — `BLOCKED`. Replay не выполняет commands.

## Required evidence

Нужна новая Manual сессия с одной и той же `session_id` и `trace_id` во всей цепочке:

`SessionStarted → PhaseTransition → DeltaStarted → DeltaCompleted → HoldStarted → HoldCompleted → TerminationDetected → SessionStopped`.

Дополнительно требуются telemetry correlation, RD readback, ESP/HA snapshots и
UI session isolation.

## Safety

V3 control, ownership transfer, Canary, lease takeover и physical commands не
выполнялись. `CB-EVIDENCE-001` остаётся открытым.
