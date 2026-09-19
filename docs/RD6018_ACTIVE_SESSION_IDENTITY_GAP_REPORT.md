# RD6018 Active Session Identity Gap Analysis — WORKSTREAM 25

## Итог

**SESSION_IDENTITY_GAP_IDENTIFIED**. Источник потери identity найден: текущая активная `Baic72/MIX` идёт по managed Manual path, а не через автоматический `ChargeControllerV2` trace path.

Runtime, FSM, START/STOP, persistence writes, physical execution и ownership не изменялись.

## Identity source inventory

| Source | Owner | Lifecycle | Persistence | Availability |
|---|---|---|---|---|
| `ChargeControllerV2._v2_trace_session_id` | V2 automatic controller | created on automatic `start/start_custom`; restored on V2 restore | written into legacy session document and recovery trace DB when enabled | available for automatic V2 path |
| `ChargeControllerV2.recovery_trace_context` | V2 automatic controller | per automatic/recovered trace | consumed by `record_shadow_trace` | available conditionally |
| `recovery_trace_store.trace_points.session_id` | recovery trace persistence | sample-level trace session | SQLite `rd6018.db` | available only when trace capture is active and samples are recorded |
| `manual_mode.ProductionManualSessionManager` state | managed Manual authority | `IDLE/ARMING/ACTIVE/COOLING/STOPPED` | `manual_session_v2.json` | present, but no identity fields |
| `charging_history.log` | legacy history logger | event text/time | text log | timestamps/events present; no session/trace IDs |
| `v3_core.observability.TraceContext` | V3 diagnostics | created by V3/UI contracts | in-memory diagnostic event context | not bound to V2 Manual runtime |
| HA/ESP/RD telemetry | external/V2 transport | sample timestamp/source | source-side state only | live values available; no V2 Manual session identity |

## Active Baic72/MIX trace

The persisted record contains `state=active`, battery `Baic72`, stage `mix`, `started_at` and `saved_at`. It does not contain `session_id` or `trace_id`.

### Where identity should appear

- At Manual `start()` before/with the first persisted active state: session identity and root trace identity.
- On every Manual transition/event: same session identity plus event trace/correlation.
- In `manual_session_v2.json`: durable session identity for restore correlation.
- In history/diagnostics: identity fields alongside `SESSION_START`, phase, Delta, Hold and STOP records.
- In telemetry/readback evidence: session/trace references attached by observer correlation, not by changing hardware.

### Classification

Primary classification: **LEGACY_MANUAL_PATH / NOT_CREATED**.

`manual_mode.py` persists state/request/timestamps but `_document()` has no `session_id` or `trace_id`; `_restore_as_interrupted()` restores state/request only and does not create an identity. Therefore the identity is not merely hidden in the current Manual JSON—it is not created by that path.

Secondary classification: **CREATED_NOT_STORED / STORED_NOT_EXPOSED** applies only to the separate automatic V2 path in cases where the trace identity exists in controller memory or recovery trace storage but is absent from the operator-facing/manual evidence surface.

## Manual start path

`ProductionManualSessionManager.start()` sets state to `ARMING`, records `started_at`, persists the request, calls the existing V2 safe enable, then transitions to `ACTIVE` and persists again. It does not call `_begin_trace_identity`, `TraceContext.create`, `record_shadow_trace` or a canonical event writer. This differs from `ChargeControllerV2.start/start_custom()`, which explicitly calls `_begin_trace_identity()` and initializes the V2 shadow trace runtime.

Manual transitions are logged as text (`MANUAL_TRANSITION old/new/reason/timestamp`) but without session/trace identity. `charging_history.log` similarly stores text event metadata without those IDs.

## Restore path

Manual restore `_restore_as_interrupted()` loads the legacy JSON and marks an old active state as interrupted requiring operator reauthorization. It does not create a new identity or preserve an old one because the file has neither field. Automatic V2 restore is different: `ChargeControllerV2.try_restore_session()` reads V2 trace fields or deterministically derives a recovery ID, then writes the identity back to its legacy session document.

Thus Manual restore is identity **LOST_ON_RESTORE / LEGACY_MANUAL_PATH**, while automatic V2 restore has an identity-preserving path.

## Minimum V3 parity requirement — no implementation here

1. Observer-side adapter must derive a provisional identity only when source evidence is explicit; it must mark missing/ambiguous identity rather than guess.
2. Manual event/history source needs a stable correlation anchor supplied by V2 or an explicit operator/session boundary; timestamp-only matching is insufficient.
3. Restore evidence must distinguish `restored` from a new `started` session.
4. Every canonical event/telemetry/diagnostic record needs `session_id`, `trace_id`, timestamp and source correlation.
5. Persistence migration is required only if V2 behavior is later authorized to store identity; this workstream does not change the legacy JSON.

## Conclusion

`CB-EVIDENCE-001` is blocked by a concrete legacy Manual identity gap, not by missing ESP/HA access. The automatic V2 controller has a separate trace identity implementation; the active Baic72 Manual path does not use it. No runtime fix is applied in this analysis workstream.
## WORKSTREAM 26 update

Design-only boundary определён: `ManualSessionIdentityBoundary` и `ManualSessionEventBridge`. Полная persisted identity восстанавливается только явно; legacy Manual restore без identity остаётся `AMBIGUOUS`. Реализации в V2 runtime нет, поэтому gap фактически не закрыт этим workstream.

## WORKSTREAM 27 update — Manual identity runtime observation

Статус: **BLOCKED**. Read-only inspection подтвердил, что `ProductionManualSessionManager` не подключает Workstream 26 boundary и не публикует identity-bearing canonical events. Observer/evidence contract подготовлен отдельно; новая Manual сессия не запускалась, поэтому `MANUAL_IDENTITY_RUNTIME_VALIDATED` не заявляется.
