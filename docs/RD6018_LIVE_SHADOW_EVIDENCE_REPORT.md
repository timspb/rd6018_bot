# RD6018 V3 Live Shadow Evidence Report — WORKSTREAM 12

## Status

**BLOCKED** — the read-only evidence pipeline is implemented and tested, but no
live installation was contacted in this workstream. Therefore this report does
not claim real telemetry, readback, lease or session evidence.

## Runtime boundary

V2 remains production, decision, execution and physical owner. V3 remains an
observer/analyzer. The collector accepts supplied snapshots and comparison
results in memory; it does not connect to HA, ESPHome or RD, persist restore
state, renew a lease, or issue commands.

## Prepared pipeline

`External sources -> supplied telemetry/readback observations -> V3 normalization
-> ShadowEvidenceRecord -> comparison/dashboard view`

The record preserves timestamp, trace ID, session ID, deterministic input hash,
source, comparison result and diagnostic references. Session evidence preserves
profile, phase timeline, telemetry history and meaningful transitions.

## Evidence not yet collected

- live ESPHome/HA/RD telemetry and freshness;
- physical readback and delayed/mismatched states;
- phase, Delta and hold timelines;
- lease owner/renewal/expiry observations;
- watchdog, transport-loss and emergency-path evidence;
- real V2/V3 divergence records.

## Next controlled read-only step

Feed timestamped snapshots from the existing installation into the collector,
attach the existing DiagnosticsDomain trace/session identifiers, and review the
dashboard view. No automatic decisions or commands are permitted. Any physical
bench step needs a separate explicit approval and rollback plan.

## Guardrails

No V2 runtime, START/ACTIVE, HA ownership, ESPHome ownership, lease ownership or
physical output was changed. Evidence is analytical data only and cannot be used
as runtime restore state. `PRODUCTION_READY` is not issued.
