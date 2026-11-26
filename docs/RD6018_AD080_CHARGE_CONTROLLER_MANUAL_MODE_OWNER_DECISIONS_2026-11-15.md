# P1-AD080 — Charge controller and Manual mode owner decisions
Date: 2026-11-15
Status: Manual host owner approved with narrow exclusion; charge controller remains NO FILE-LEVEL APPROVAL. No code movement.

## Whole-file decisions

| Module | Decision | Primary owner / reason |
|---|---|---|
| charge_controller.py | **NO FILE-LEVEL APPROVAL** | It is the one canonical production ManagedChargeController host, but combines multiple existing owner groups and remains a broad mutable integration surface. It is not a stateless facade, but it is not a second controller or canonical writer. |
| manual_mode.py | **APPROVE WITH NARROW EXCLUSION** | Application owns the one ManualSessionManager workflow/state host and compatibility bridge. Exclude legacy UI label/config DTO details and keep all accepted delegated owners in place. |

## charge_controller.py — function-group ownership

- **Canonical host construction and state projection:** the single production ManagedChargeController is constructed in runtime/production_runtime.py:313 and installed by production_bootstrap.py:161-164. Charge Engine / Charge Stages owns stage policy; Sessions & Persistence owns session lifecycle and serialized state; the controller is the host-facing projection/composition surface. Keep one instance.
- **Start/stop/session reset lifecycle:** Sessions & Persistence via runtime/charge/lifecycle.py. Controller methods delegate; they do not become a second lifecycle engine.
- **Canonical save/restore facade:** Sessions & Persistence via runtime/charge/persistence.py. _save_session and try_restore_session are delegates. Do not treat save_session as a commit receipt; AD071/AD076 START atomic replacement remains open.
- **Target selection and stage policy adapters:** Engine / Charge Stages through existing runtime/charge/strategy modules. Controller dispatches to these policies and keeps compatibility wrappers; it does not own the underlying target rules.
- **Safe-wait, recovery context, trace and evidence:** Engine / Charge Stages owns transitions; Telemetry owns supplied samples/provenance; Recovery & Ownership owns recovery trace identity and shadow models. Controller composes the existing host state.
- **Verified transition application:** Application validates session-bound continuation and applies software state only after its caller reports verified enable; Physical Execution / ExecutionPort owns actual effect and verification. commit_verified_enable_transition does not issue hardware I/O.
- **Diagnostics and UI snapshots:** Application/Telemetry/UI read-model owners. These are compatibility projections, not independent state authority.
- **Physical effect exclusion:** source inspection found no direct HA setter, ESP Native API, Modbus write or ExecutionPort invocation in charge_controller.py. It exposes targets/intents and verified-transition application only.

**Important state-boundary finding:** charge_controller.py still stores broad host state and production_runtime.py mutates private fields directly: _was_unavailable, _link_lost_at, _last_known_output_on, _device_set_voltage and _device_set_current (runtime/production_runtime.py:827-830,902-910,1404-1428). This makes the host more than a stateless facade, but does not create a second ManagedChargeController. Safest next P1 slice is a field-level caller/owner contract for these exact runtime fields and START mutation fields; do not move methods mechanically or create a second host.

## manual_mode.py — Application owner with exclusions

Application owns the one live ManualSessionManager host, its in-memory Manual state transitions, identity/event projection, and delegation to the existing Application use cases. Production bootstrap constructs one ProductionManualSessionManager and one ProductionManualUIRoute (production_bootstrap.py:195-197). The production subclass extends the base manager; it is not a second manager.

- Manual state and request lifecycle: Application owns ManualSessionManager's single runtime state (state, request, start/pause/cooling/stop reasons, task, Delta inputs, MAIN confirmation mirror and one ManualPhaseLifecycle instance).
- Persistence: Sessions & Persistence owns JSON read/write through runtime/charge/manual_session_store.py. ManualSessionManager owns the projection and interrupted-on-restart policy; it does not own file I/O.
- MAIN→MIX lifecycle: Engine / Charge Stages owns ManualPhaseLifecycle under AD016/AD019. Do not duplicate its transition logic.
- Delta and phase evidence: runtime/charge/evidence/manual_delta.py and application/manual_phase_evidence.py remain unapproved under AD069. This decision does not approve them or move their evidence rules into the manager.
- Cooling/MIX/START/STOP: the AD069-approved Application use cases remain the workflow owners. ManualSessionManager delegates; no new use case or manager.
- Observer/Supervisor: the AD069 holds on manual_observer_use_case.py and manual_supervisor_use_case.py remain. The single supervisor task is launched by the existing start use case; no second poller.
- UI ingress: ProductionManualUIRoute / manual_text.py owns live routing; ManualUIIntent and ManualChargeRequest are request DTOs. Narrow exclusion: Russian presentation labels, local UI limits and legacy request-intent configuration values are not reclassified by this approval.
- Physical effect: the manager obtains the canonical ExecutionPort and ManualExecutionBoundary. Reviewed workflows route through ExecutionPort; no direct HA/ESP/Modbus write is present in manual_mode.py.

### Concrete persistence-boundary defect

ProductionManualSessionManager._restore_as_interrupted in manual_runtime.py:159-174 directly opens and parses the same Manual JSON document to recover reach_voltage_v/reach_current_a, then calls the base restore path. The accepted runtime/charge/manual_session_store.py already exposes read_manual_session_document(path) at :17-29. This is a second read implementation, not a second writer. Safest next slice: route this reach-target read through the existing store reader, retaining the same schema and failure behavior. No new store, reader package or writer.

The store writer remains Sessions & Persistence: write_manual_session_document performs temp-file write, flush/fsync, os.replace and best-effort directory fsync (manual_session_store.py:50-83). AD016/AD019/AD021/AD023 semantics remain unchanged: one lifecycle object; exact session identity; pure MIX hold predicate; separate adopted-MIX epoch; reset all Delta tracking only after verified cooling OFF.

## Test evidence and limits

AD077 inspected the test inventory recorded in .recipe-studio-local/REPORT_MOD_P1_AD077_CHARGE_CONTROLLER_MANUAL_MODE_AUDIT_20261115_FULL.md. All tests are **NOT RUN** in this decision. Existing tests cover controller lifecycle/targets, production controller composition, session save/restore, Manual state/task behavior, session-store atomic write, extracted use-case delegation, Delta epoch and phase lifecycle, UI routing and source/AST ownership contracts. AST/HEAD parity tests are structural/historical evidence, not proof of current production ownership or physical behavior.

No tests run, no source/test/doc/CSV/registry/generated changes, no HA/ESP Native/network/hardware/firmware/node104/deployment. No new manager/store/writer/poller/lock. Branch/HEAD unchanged, all dirty WIP preserved. START/release HOLD.

## P1 cumulative census

AD080 adds one primary/effective file-level owner approval for manual_mode.py. Cumulative source-reviewed owner decisions: **45 primary / 66 effective / 433 pending**; high-risk **31 approved / 12 explicitly unapproved / 30 blank-pending**; critical 15/15. These are manual cumulative counts from AD061 baseline plus accepted AD062–AD080 decisions, not a live read of the stale AD014 sidecar/AD012 generated CSV. Those historical files remain untouched.
