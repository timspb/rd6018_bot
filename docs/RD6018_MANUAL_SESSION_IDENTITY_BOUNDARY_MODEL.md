# RD6018 Manual Session Identity Boundary — WORKSTREAM 26

## Scope

Design/contract only. `ProductionManualSessionManager`, charge algorithm, FSM, START/STOP, persistence writes, physical execution and lease ownership are not changed.

## Current Manual path

Manual `start()` changes `IDLE → ARMING → ACTIVE`, persists request/state/timestamps and runs the existing safe-enable path. Restore reads `manual_session_v2.json`, restores request/state and marks an old active state as interrupted for operator reauthorization. The legacy document has no canonical session/trace identity.

## ManualSessionIdentityBoundary

The boundary carries:

- `session_id`;
- `trace_id`;
- `created_at`;
- `source`;
- `profile`;
- `origin`: `manual_start`, `restored`, `resumed`;
- optional `linked_session_id` for explicit resume linkage.

Identity is created in the future contract at an explicit Manual start or resume boundary. It is not silently generated while merely observing an old persisted state.

## Restore semantics

1. Complete persisted identity (`session_id + trace_id + created_at`) → `RESTORE_EXISTING`.
2. Legacy persisted state without complete identity → `AMBIGUOUS`; no guessed identity and no fake START.
3. Explicit operator-approved resume may create `RESUMED` identity with `linked_session_id`; this is a future contract, not implemented here.

## ManualSessionEventBridge

The bridge maps only explicit Manual events to `CanonicalChargeEvent`, carrying identity, source, phase, reason and telemetry reference. It does not emit lifecycle events that were not observed and does not call runtime, persistence, HA, ESPHome or physical layers.

## Evidence impact

Before: active Manual session is state/profile/time capable but identity-free.  
After contract adoption: a newly observed Manual session can be identity-capable and contribute canonical events. `CB-EVIDENCE-001` is not closed by this design alone; a real identity-bearing complete cycle is still required.

## Safety rules

- no automatic ownership transfer;
- no implicit identity creation on restore;
- no history rewrite;
- no synthetic START/STOP/Delta/Hold events;
- ambiguous records remain ambiguous;
- V2 remains production owner.

Status: **MANUAL_IDENTITY_BOUNDARY_DEFINED**.
