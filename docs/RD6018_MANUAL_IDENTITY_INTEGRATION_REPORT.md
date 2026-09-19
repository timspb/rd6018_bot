# RD6018 Manual Identity Boundary Integration — WORKSTREAM 28

## Status

`MANUAL_IDENTITY_INTEGRATION_READY`.

The integration is limited to lifecycle identity, compatible persistence and
in-memory canonical event exposure. V2 remains the production execution,
control, lease and physical owner.

## Changes

`ManualIdentityIntegrationAdapter` is attached to
`ProductionManualSessionManager` and:

- creates a fresh `session_id`/`trace_id` for each new Manual start;
- exposes identity and canonical events to evidence consumers;
- emits `SessionStarted`, `PhaseTransition` and `SessionStopped` observations;
- restores a complete `session_identity` as `RESTORE_EXISTING`;
- leaves legacy records without identity as `AMBIGUOUS`;
- writes only an optional `session_identity` field; old JSON remains readable.

Identity and event operations are in-memory/contract-level. They do not call
HA, ESPHome, lease, controller or physical adapters.

## Preserved behavior

Charge algorithms, FSM transitions, profile/strategy decisions, START/STOP
control semantics, actuator calls and lease ownership were not redesigned.
The existing safe-enable and stop paths remain the production authority.

## Evidence impact

New Manual sessions are now identity-capable for downstream observation. Legacy
active sessions are not migrated and do not receive a guessed identity or a
synthetic START. `CB-EVIDENCE-001` still requires a real V2-owned session
capture proving the complete correlated chain.
