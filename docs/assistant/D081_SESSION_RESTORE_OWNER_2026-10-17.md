# D081 — link-session recovery policy owner

`runtime.charge.link_session_recovery` owns the pure deterministic decisions for
the three link/session recovery routes in `runtime.production_runtime.data_logger`.
Its frozen inputs and enum outputs contain no application, client, logger,
strategy, or execution dependencies. It selects a route before any persisted
session mutation, then selects a post-restore action after the existing
`restore_allows_auto_enable()` authority has been evaluated.

## Route map

| Route | Selection | Existing effects retained in `production_runtime` |
| --- | --- | --- |
| A — active in-memory lost-link session | Active stage, link was unavailable, Output is not ON, temperature is available; DONE and COOLING are excluded. | Target calculation, phase protection, ExecutionPort programming, verified ON, restore time correction and existing event/notification behavior. Protection alarms and the existing input-voltage comparison still gate this route. |
| B — lost-link IDLE session | Link was unavailable and stage is IDLE; selected before `try_restore_session()`. | Persisted restore and time correction remain in their current order. Canonical `restore_allows_auto_enable()` remains authoritative. SAFE_WAIT retains target/protection programming followed by verified OFF; other eligible stages use the existing programmed verified-ON path. Declines retain existing alarms and notifications. |
| C — IDLE while Output is already ON | Link was not unavailable, stage is IDLE, Output is ON and current exceeds 0.05 A; selected before `try_restore_session()`. | Restore and authorization remain in their current order. SAFE_WAIT retains verified OFF; other eligible stages are programmed through the existing execution port without an Output ON request. |

The operator-pause gate remains outside and before all three routes. The route
selector consumes the runtime's existing `output_on` boolean, preserving the
current treatment of unknown Output status. It does not infer ON from unknown
telemetry. Missing/disabled temperature prevents route selection. DONE and
COOLING remain excluded from route A; persisted DONE/COOLING authorization
continues to belong to the existing restore policy. No startup deferred restore
behavior was moved or merged into link recovery.

## Boundary and evidence

The policy does not calculate charge targets, interpret temperature, change
timing, write persistence, log, notify, call the execution port, or actuate
hardware. Production remains the sole orchestrator and all physical effects
remain behind the existing `ExecutionPort` boundary. No lease, watchdog,
recipe, AGM, MIX, or output safety behavior was changed.

The next ownership seam is the remaining orchestration/effects block in
`data_logger`. Consider extracting it only if it can receive explicit immutable
runtime evidence and keep all effects at the existing execution boundary;
there is no second restore facade or separate startup-recovery policy to add.
This change is software-only and supplies no physical validation evidence.
