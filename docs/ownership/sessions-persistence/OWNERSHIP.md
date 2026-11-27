# Sessions / Persistence — ownership contract

**Status: operating boundary documented; department functional-owner approval OPEN.** Primary ADRs remain the decision authority. This file records accepted decisions and conservative inventory classifications; placement under this department does not assign ownership.


### B902 current P1 scope reconciliation (2026-11-25)
AD083 D061 function scopes are accepted with the boundaries recorded in `docs/RD6018_AD083_CONTROL_ADOPTION_OWNER_DECISIONS_2026-11-15.md`. The file has no whole-file owner. D062 MIX authority remains separate in `rd_managed_mix.py`. The current 517-row source registry and historical 82-path subset were reconciled from B900 evidence; no registry-wide reanalysis was repeated.

## Responsibility and boundaries

- Planned responsibility: Sessions / Persistence as defined in `docs/RD6018_MODULARIZATION_EXECUTION_PLAN_P0-P9_2026-11-17.md` (department table, lines 12–24).
- The production functional owner, cross-department state/decision owner map, and final whole-file owner assignments remain OPEN unless an exact primary ADR below approves the bounded responsibility.
- Interfaces are the existing function/module APIs cited per path; this contract authorizes no file moves, API changes, new state, side effect, or compatibility shim.
- Consumers, callsites, side effects, and dependencies are summarized from the AD148AN source/call graph review. Verify against current source before implementation; this checkout has extensive dirty WIP.

## State, decisions, and interfaces

- State and decisions remain with their specifically cited existing owners. Only a row still classified CANDIDATE / NOT APPROVED is unapproved; APPROVED path rows are limited to the cited primary ADR scope. Cross-department orchestration stays with existing callers and ports.
- Inputs/outputs follow current callable signatures and DTOs; no inferred API expansion is approved. No UI/Application direct hardware access; physical effects remain behind existing execution boundary.

## Consumers, effects, dependencies, tests, migration

- Exact source paths and caller/test evidence are listed in the inventory below. These paths are evidence pointers, not authorization to change them.
- Migration constraint: preserve current public imports, persisted formats, operation order, safety/verified-OFF semantics, and caller behavior. Any future extraction needs a separate bounded ADR and focused parity tests.
- Risk: matrix source observations came from a dirty checkout; candidate recommendations are not approvals, and some rows lack production reachability evidence.

## 2026-11-25 — B900 current functional scope reconciliation

The B900 review records accepted function/module scopes against current production callers and the cited primary decisions. These entries do not imply blanket department sign-off or whole-file approval. The current 517-row source registry and historical 82-path approval subset were reconciled from existing B893/B899 ledgers; categories were mapped without replaying or double-counting prior rows. B902 accepts the bounded D061 function scopes in `rd_managed_adoption.py` after false/exception/cancellation verification; its whole-file owner remains intentionally blank, and D062 MIX authority remains in `rd_managed_mix.py`.

## Path assignment register

## 2026-11-19 — P7 OFF preset mutation owner, batch 20 (acceptance pending)

- Existing `runtime/operator/off_conditions.py::OperatorOffConditions` now owns named OFF preset definitions, validation, mutation, clear behavior, and exact success text through `apply_preset()`. The existing runtime `_apply_manual_off_preset()` remains the compatibility delegate and retains `_save_manual_off_state()` for persistence.
- Existing six-key legacy JSON format/path, `time_2h` 7200-second duration with call-time start, `i_le_030` 0.30 A, `v_ge_162` 16.2 V, clear behavior, and error strings are preserved. Unknown/invalid input clears and persists before raising. No Output action or trigger authority changed.
- Source/fake tests pass on Linux; native Windows acceptance pending. This is a bounded API implementation record and does not assign a new whole-file/department owner or change AD148 HOLD.

| Classification | Path | Primary ADR / scope | Caller evidence / tests |
|---|---|---|---|
| REGISTER NOTE | — | Individual path decisions appear below; department functional-owner sign-off remains OPEN. |
| APPROVED (whole-file final owner) | `runtime/charge/manual_session_store.py` | AD010 lines 9, 13 — Sessions & Persistence owns the existing JSON document read/write and atomic replace API. Current restore parses once and shares that document; schema interpretation and workflow remain with ManualSessionManager/runtime callers. | `manual_mode.py` persists and restores; `manual_runtime.py` reads through the same API. Tests: `tests/test_modularization_manual_session_store.py`, `tests/test_modularization_manual_session_store_cutover.py` |
| BOUNDED AD014 — whole-file owner remains blank | `runtime/operator/pause_state.py` | AD014, lines 3, 11; AD146, line 18 — sidecar state/persistence only; transaction ordering stays Application; whole-file owner remains blank. | Atomic timestamp sidecar; one state instance in production_runtime.py, startup load in lifecycle and update from the Application pause use case. Tests: No path-specific test identified in this bounded matrix; focused test evidence remains OPEN. |
| APPROVED (whole-file final owner) | `database.py` | AD006 line 7 — Existing public DB API and data semantics remain the boundary. | Owns SQLite connection/schema and record operations; production runtime imports it for telemetry writes and cleanup. Tests: No path-specific test identified in this bounded matrix; focused test evidence remains OPEN. |
| MIXED-SCOPE | `diagnostic_persistence.py` | AD057, master plan line 1014 — AD057 is bounded and does not settle whole-file ownership. | Diagnostic data persistence plus related read/projection responsibilities. Tests: `tests/test_diagnostic_persistence.py` |
| APPROVED (whole-file final owner) | `charging_log.py` | AD078 whole-file decisions, line 14; scope lines 46–51 — AD078 whole-file owner decision, subject to stated storage boundary. | Existing log formatting and writes; called by production charge/session flows. Tests: `tests/test_charging_log.py` |

## Unassigned decision rules

- **APPROVED:** individually APPROVED rows are approved only within the cited primary ADR scope.
- **CANDIDATE / NOT APPROVED:** only rows still marked CANDIDATE / NOT APPROVED remain unresolved; B900 resolved the six reviewed paths at their current bounded scopes.
- **BOUNDED AD014:** preserve the five exact function/state boundaries and keep whole-file final owner blank.
- **MIXED-SCOPE / ADAPTER/COORDINATOR / INSUFFICIENT-EVIDENCE:** retain their documented function scopes; do not infer whole-file owners.
- **HOLD:** `rd_managed_adoption.py` retains AD083 function boundaries and its concrete D061 verified-OFF containment gap; no whole-file owner is assigned.

## Sources

- `docs/RD6018_MODULARIZATION_EXECUTION_PLAN_P0-P9_2026-11-17.md` — canonical department names, P1 checklist and status.
- `.recipe-studio-local/REPORT_MOD_P1_AD148AN_FINAL_OWNER_MATRIX_20261117.md` — 81-path evidence/classification matrix; recommendations only.
- `.recipe-studio-local/REPORT_RD6018_P1_FINAL_OWNER_PERSISTENCE_RESOLUTION_20261118.md` — 37/5/39 reconciliation and approved persistence model.
- Exact primary ADR references are recorded per path above; ADR text, not this summary, governs scope.


## 2026-11-18 — P1/P2 Manual durable store: verified single-read restore, source/fake

- Reviewed `runtime/charge/manual_session_store.py`, `manual_mode.py` and `manual_runtime.py` against existing primary AD010/AD010A and AD080 and the current production constructor/call graph. The historical P1-AD148AF/AD129 note about two reads is **obsolete in current HEAD**: `ProductionManualSessionManager._restore_as_interrupted` calls `read_manual_session_document` once and passes `raw_document=raw, document_loaded=True` to the base `ManualSessionManager`; the base skips its own read. Both subclass reach-field projection and the base identity/request restore therefore consume the **same parsed document**. The single write remains `ManualSessionManager._persist` through the atomic `write_manual_session_document`, with subclass reach fields included via `_document`. No alternative file/JSON serialization owner was found in the two managers.
- Added two failure/compatibility tests in `tests/test_manual_runtime.py`: corrupt JSON uses exactly one store read and **no rewrite/no Output enable**, and STOPPED document restores reach fields with exactly one read and no terminal rewrite/Output enable. Existing ACTIVE restore test already proves one read, no base reread and exactly one INTERRUPTED rewrite.
- Independent Windows project venv three-module cohort `test_manual_runtime.py`, `test_modularization_manual_session_store.py`, `test_modularization_manual_session_store_cutover.py`: **33 PASS + 12 subtests PASS**, exit 0. This closes an outdated evidence gap, not a new production refactor.
- The Manual storage and restore *functional boundaries* are evidenced, but prior AD148AF `INSUFFICIENT-EVIDENCE` classification is **not mechanically promoted to final_owner**. Primary AD010 approves the narrow module owner; AD080 and its bounded caveats still govern multi-department responsibility. AD148T diagnostic `resolved_final_owner` remains blank; AD014 bounded five, AD083 HOLD, and unrelated 39 unassigned paths unchanged. P1/P2 overall OPEN.
- This remains source/fake evidence, not verified hardware restart/Output admission. Future BW600 load telemetry and switch state must use separate integration contracts; not a new field in the Manual session store. No node104, ESP/HA, Output, setpoint, lease, firmware or deploy.


## 2026-11-19 — independent P7 OFF preset owner batch-20 acceptance

- HOME-PC Codex Luna run `rd6018-mod-p7-operator-off-preset-owner-luna-20261119-20` exited 0; completion event observed in controlling chat. Existing `OperatorOffConditions.apply_preset()` now owns preset documents, validation, clear/unarm, exact success text. Legacy `_apply_manual_off_preset()` delegates and persists via existing save hook, with no actuator operation or duplicate state.
- Native Windows project `.venv` original eight-module baseline before change **63 PASS + 32 subtests PASS**. Independent same cohort after change **65 PASS + 34 subtests PASS**. Expanded eleven-module OFF/runtime notification/entrypoint/panel suite **108 PASS + 105 subtests PASS**, exit=0. Python compilation and git diff whitespace PASS.
- P7 OFF preset source/fake subgate ACCEPTED. P7 composition/notification owner and AD148 final-owner remain OPEN; P8 full Linux/physical/release HOLD. No node104, live HA/ESP, Output, setpoints, charging, lease, firmware, deployment or remote push.
