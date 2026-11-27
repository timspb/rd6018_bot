# P1-AD148S — Evidence-based owner chronology reconstruction

Date: 2026-11-17  
Disposition: **chronology reconstructed for explicit file-level decisions; registry publication remains HOLD**.  
Scope: read-only source/document audit. No CSV, ADR, generator, source, tests, or hardware files changed.

## Executive finding

The 17 extra AD006-field entries in the materialized AD014 CSV must not be described as unauthorized. The primary decision chronology explicitly approves exactly those 17 files: 11 in the 2026-11-14 AD056 owner list and six in the 2026-11-14 AD057 list. AD056 records 16 total primary approvals at that point; AD057 records 22. This matches AD006's original five plus 17 later AD056/057 approvals. The materialized CSV's value 22 in the old `approved_primary_owner` column therefore reflects later decisions written into an older field; it does not prove the historical AD014 generator output was altered by an unauthorized actor.

The distinct registry generations/counts are:

| Artifact / stage | Paths | Primary-owner evidence | `final_owner` | Meaning |
|---|---:|---:|---:|---|
| AD010 sidecar | 481 | AD006=5, AD008=10, AD010=6 | 0 | Frozen earlier registry generation |
| AD012 sidecar | 499 | same 21; AD014 fields absent | 0 | Coverage baseline; 18 additions, not approvals |
| AD014 generator's intended output | 499 | AD006=5 + AD008=10 + AD010=6 + AD014=5 = 26 | blank by generator contract | Historical AD014 snapshot |
| Current materialized AD014 file | 499 | old AD006 column=22 plus AD008=10, AD010=6, AD014=5 = 43 distinct nonempty approval-field paths | 17 | Mixed-time overlay: 26 AD014 baseline plus 17 AD056/057 decisions, with `final_owner` copied from those 17 primary approvals |

Accordingly, “26 vs 43” is not a conflict between two approval decisions. 26 is the canonical AD014 snapshot. 43 is the current union of nonempty approval columns in a later-mutated materialized file and includes 17 later AD056/057 approvals. Neither count includes the later independently documented AD062+ decisions. The generator `tools/architecture/reconcile_owner_decisions_ad014.py` is explicit: it validates AD012 has blank `final_owner`, requires exactly five AD006 entries, appends only AD014 fields and five AD014 decisions, and renders 26 total approvals.

## Path ledger: AD056 and AD057

Provenance for every row below: `docs/RD6018_MODULARIZATION_MASTER_PLAN_2026-11-12.md`, headings **“2026-11-14 — AD056 owner-gate reduction and safety/readback reconciliation”** (11 primary-owner approvals) and **“2026-11-14 — AD057 critical owner closure + P7 read-model extractions”** (six new primary-owner approvals). The handoff canon and runbook repeat the same lists under those headings. These are approved-primary classifications, not blanket final/effective ownership of every responsibility in each mixed file.

| Path | Approved primary owner | Stage / status / scope |
|---|---|---|
| `application/controller_action_execution.py` | Application | AD056; approved primary |
| `application/controller_session_retirement.py` | Recovery & Ownership | AD056; approved primary |
| `application/execution_intent/policy.py` | Safety Authority | AD056; approved primary |
| `application/safe_output_coordinator.py` | Physical Execution | AD056; approved primary |
| `runtime/safety/strict_guard.py` | Safety Authority | AD056; approved primary; standalone Strict distinction retained |
| `runtime/safety/managed_guard.py` | Safety Authority | AD056; approved primary; canonical managed protection owner |
| `application/execution_port.py` | Physical Execution | AD056; approved primary |
| `application/session_recovery_service.py` | Recovery & Ownership | AD056; approved primary |
| `runtime/startup_recovery.py` | Recovery & Ownership | AD056; approved primary |
| `runtime/production_lifecycle.py` | Composition/Config/Deploy | AD056; approved primary |
| `application/main_guard_transaction.py` | Physical Execution | AD056; approved primary; reaffirmed, not recounted, at AD071 |
| `diagnostic_persistence.py` | Sessions & Persistence | AD057; approved primary |
| `diagnostic_probe.py` | Application | AD057; approved primary |
| `hass_api.py` | Integrations | AD057; approved primary |
| `rd_managed_adoption.py` | Recovery & Ownership | AD057 initially; later status superseded/narrowed by AD083 (see below) |
| `rd_managed_mix.py` | Recovery & Ownership | AD057; approved primary; adoption coordinator, not raw physical owner |
| `runtime/production_runtime.py` | Composition/Config/Deploy | AD057; approved only as legacy runtime namespace/composition-root compatibility surface; explicitly mixed/decomposition-required |

The 17 path set and counts exactly match the 17 extra AD006-field and `final_owner` rows observed in the materialized AD014. The path-level chronology supports their legitimacy as primary approvals. The audit did not establish when, by whom, or through what process those later values were materialized into the historical CSV.

## Subsequent explicit primary-owner decisions

Exact paths and owner labels below are from each ADR's **Decision(s)** section. “Approved” means primary file-level approval unless qualified; AD064, AD072, AD087, AD089, AD092 and AD147 are not additional file-level approvals.

| Stage | Explicit approved primary path(s) → owner | Provenance / qualification |
|---|---|---|
| AD062 | `runtime/charge/evidence/recovery_plateau_observer.py`, `runtime/charge/evidence/recovery_plateau_policy.py` → Telemetry | ADR `docs/RD6018_AD062_RECOVERY_PLATEAU_EVIDENCE_OWNER_2026-11-15.md`, Decision; source ownership classification only |
| AD063 | `application/main_guard_runtime.py` → Application | ADR `docs/RD6018_AD063_MAIN_GUARD_RUNTIME_OWNER_2026-11-15.md`, Decision; one-shot orchestration only |
| AD064 | none | Test-contract correction only; production ownership unchanged |
| AD065 | `runtime/charge/strategy/main_authority.py` → Engine / Charge Stages | ADR `docs/RD6018_AD065_MAIN_TRANSITION_AUTHORITY_OWNER_2026-11-15.md`, Decision |
| AD066 | none new | Existing reader moved into persistence owner, but AD066 is a bounded source-owner split, not a new primary approval |
| AD067 | `runtime/charge/restore_finalization.py` → Application | ADR `docs/RD6018_AD067_RESTORE_FINALIZATION_OWNER_2026-11-15.md`, Decision; `restore_projection.py` explicitly HOLD/no file-level approval |
| AD069 | `application/manual_cooling_use_case.py`, `application/manual_mix_transition_use_case.py`, `application/manual_start_use_case.py`, `application/manual_stop_use_case.py` → Application | ADR `docs/RD6018_AD069_MANUAL_WORKFLOW_OWNER_DECISIONS_2026-11-15.md`, Decisions; five other modules held at that stage |
| AD071 | `application/start_transaction_runner.py`, `application/start_transaction_adapter.py`, `application/charge_session_tick.py` → Application | ADR `docs/RD6018_AD071_START_CHAIN_OWNER_DECISIONS_2026-11-15.md`, Decisions; `start_transaction_service.py` remains HOLD; `main_guard_transaction.py` is AD056, not new |
| AD072 | none | Cancellation settlement decision; START remains OPEN, no owner approval |
| AD073 | `application/operator_recovery_clearance.py` → Application; `application/session_recovery_guard.py`, `runtime/journal/recovery_quarantine.py` → Recovery & Ownership | ADR `docs/RD6018_AD073_RECOVERY_QUARANTINE_OWNER_DECISIONS_2026-11-15.md`, Decisions |
| AD076 | none at file level | Session and persistence function-group ownership only; both complete files explicitly remain unapproved |
| AD078 | `runtime/charge/diagnostics.py` → Application (narrow Safety exclusion); `runtime/telemetry/recorder.py` → Telemetry; `signal_analyzer.py` → Engine / Charge Stages; `recovery_trace_report.py`, `recovery_session.py` → Recovery & Ownership; `charging_log.py` → Sessions & Persistence | ADR `docs/RD6018_AD078_TELEMETRY_SIGNAL_DIAGNOSTICS_OWNER_DECISIONS_2026-11-15.md`, Whole-file decisions; all bounded as described there |
| AD080 | `manual_mode.py` → Application | ADR `docs/RD6018_AD080_CHARGE_CONTROLLER_MANUAL_MODE_OWNER_DECISIONS_2026-11-15.md`, Decision; narrow exclusions; `charge_controller.py` remains unapproved |
| AD082 | `runtime/safety/engine.py`, `runtime/safety/edge_lease.py`, `runtime/safety/output_policy.py`, `runtime/safety/critical_telemetry.py`, `runtime/safety/telemetry_recovery.py`, `runtime/safety/temperature_integrity.py` → Safety Authority | ADR `docs/RD6018_AD082_SAFETY_AUTHORITY_OWNER_DECISIONS_2026-11-15.md`, Decisions; exclusions are part of the approval; `runtime_guard.py` remains unapproved |
| AD083 | `rd_control_mode.py`, `rd_live_adoption.py`, `edge_live_adoption.py` → Recovery & Ownership; `rd_managed_mix_adoption.py` → Presentation / Telegram workflow | ADR `docs/RD6018_AD083_CONTROL_ADOPTION_OWNER_DECISIONS_2026-11-15.md`, Decisions; narrow exclusions apply |
| AD083 | `rd_managed_adoption.py` → **NO FILE-LEVEL APPROVAL / HOLD** | Later and more specific than AD057. Mixed transaction ownership and false-OFF result handling explicitly rejected a whole-file approval. AD057 remains evidence of an earlier primary classification, not current final ownership or an operative whole-file approval. |
| AD086 | none new | Function-group contract only; `runtime_guard.py` remains no file-level approval |
| AD087 | none new | Narrow implementation approval within existing owners; not a file-level owner decision |
| AD089 | none new | Same-owner cancellation-fence contract; no new file owner |
| AD092 | none new | Reaffirms bounded AD062/AD065/AD078 owner boundaries; no blanket new owner |

### AD142–AD147 crosswalk: six approvals vs eight path mappings

There are **six newly and explicitly approved files** across AD142–AD146:

1. AD142 `application/manual_supervisor_use_case.py` → Application.
2. AD143 `application/manual_observer_use_case.py` → Application.
3. AD143 `runtime/safety/thermal_variables.py` → Safety Authority.
4. AD144 `application/manual_phase_evidence.py` → Application adapter (evidence normalization/eligibility/orchestration only).
5. AD145 `runtime/charge/evidence/manual_delta.py` → Manual Delta Evidence pure transform only.
6. AD146 `application/operator_pause_use_case.py` → Application transaction orchestration.

Provenance: ADR Decision sections in `docs/RD6018_AD142_MANUAL_SUPERVISOR_OWNER_APPROVAL_2026-11-16.md`, `docs/RD6018_AD143_MANUAL_OBSERVER_THERMAL_OWNER_2026-11-16.md`, `docs/RD6018_AD144_MANUAL_MAIN_TAIL_PROGRAM_OWNER_2026-11-16.md`, `docs/RD6018_AD145_MANUAL_DELTA_EVIDENCE_OWNER_2026-11-16.md`, and `docs/RD6018_AD146_OPERATOR_PAUSE_APPLICATION_OWNER_2026-11-16.md`.

The “eight” count is reproduced only by adding two **existing owner confirmations** in AD144, not by treating them as new approvals: `runtime/charge/strategy/manual_phase_lifecycle.py` → Charge Strategy and `runtime/charge/programs/manual.py` → Manual Charge Program. AD144 also names `runtime/charge/evidence/first_stage_variables.py` as an existing owner, which makes a nine-path list if every ownership reference is counted; it does not label that path as a new file-level approval. Thus six is the count of explicit new approvals, eight is six plus two reaffirmed domains, and nine is the count if the additional First Stage Evidence reference is included. None justifies inserting all references as new approvals. AD147 is implementation acceptance under the already-approved Application/persistence owners; it adds no new primary owner. Its modified paths include `application/operator_pause_use_case.py`, `runtime/operator/pause_state.py`, and `runtime/production_runtime.py`; only the first is newly approved at AD146, the latter two are existing persistence/composition collaborators.

## Count reconciliation and duplicate semantics

- AD061's reconciled baseline is **22 primary / 43 effective**; here “effective” aggregates the four historical approval-source fields and can count a path in more than one source. It is not equivalent to `final_owner` and not a list of 43 independently approved primary owners.
- AD071 reports **35 primary / 56 effective / 443 pending** from AD061 plus accepted AD062–AD071. The primary delta is 13: AD062 (two paths), AD063 (one), AD065 (one), AD067 (one), AD069 (four), AD071 (three). AD064 and AD070 add none; AD071's AD056 reaffirmation adds none. Effective delta is likewise 13 in the recorded census.
- AD073 reports **38 primary / 59 effective / 440 pending**, exactly +3/+3 for its three explicit approvals.
- AD078 reports **44 primary / 65 effective / 434 pending**, exactly +6/+6.
- AD080 reports **45 primary / 66 effective / 433 pending**, exactly +1/+1.
- AD082 and AD083 then report 55 primary / 76 effective / 423 pending after six plus four explicit primary decisions. These are manually reconciled source-reviewed census figures, not counts read from the old AD014 CSV.
- AD056/057's local sidecar counter (16 then 22 primary) and AD061's 22-primary baseline refer to a post-AD014 review stage. The equality of 22 does not mean identical file sets or convert `final_owner` into primary ownership.
- Repeated departments, compatibility wrappers, function-group boundaries, owner reaffirmations, and already-approved paths do not create duplicate primary approvals. `final_owner` is a separate resolved-owner/legacy column; its 17 nonempty values happen to mirror the later AD056/057 primary decision set but are not themselves the approval evidence.

## Additive registry algorithm proposal (not executed)

1. Keep AD010, AD012, and AD014 byte-for-byte as historical artifacts. Re-run the AD014 generator only in memory from AD012 and verify its deterministic 499-row/26-approval result; do not accept current AD014 as input.
2. Create a new versioned additive ledger/snapshot with source-generation ID, exact source SHA-256s, path, owner, decision stage, decision document/heading, explicit status (`APPROVED_PRIMARY_OWNER_ONLY`, `RECONFIRMED`, `HELD`, `SUPERSEDED`, or `FUNCTION_GROUP_ONLY`), scope note, and whether the path existed in AD012. Preserve inventory/provenance/working-set columns from AD012 unchanged.
3. Seed the 26 canonical approvals from the AD014 generator manifest. Add the 17 AD056/057 paths from their explicit master-plan lists, each with AD056 or AD057 provenance; do not infer approval from the mutated AD006 or `final_owner` cells.
4. Apply later ADRs in chronological order, recording only decisions that explicitly approve a file-level primary owner. Keep reaffirmations as evidence events, not duplicate approvals. Record AD083's later HOLD for `rd_managed_adoption.py` as superseding the AD057 whole-file approval. Preserve all no-approval/HOLD/function-group decisions as status events, outside the approved-primary set.
5. Add the six explicit AD142–AD146 approvals. Store AD144's two (or three, if First Stage is included) existing owner confirmations as reaffirmations, not new approvals. Record AD147 as implementation acceptance tied to the AD146 owner, without adding a duplicate owner row.
6. Derive counts from unique path + current valid primary decision, with decision history retained. Derive `final_owner` only in a separate, explicit resolution pass after path-specific mixed-scope review; never copy approved-primary into final ownership automatically. Permit multiple evidence records per path but exactly one current primary owner, and make supersession explicit.
7. Emit a deterministic report with path-by-path provenance, AD012 presence/status, present-worktree and Git-tracking state, decision history, and aggregate counts. Validate that no unapproved/HOLD path enters the approved-primary set and that all source references resolve. Do not regenerate or overwrite historical CSVs.

## STOP criteria

Stop before publication if any approved row lacks an exact ADR/master-plan passage; a decision has ambiguous file-level vs function-group scope; primary owners conflict without an explicit later supersession; duplicate paths collapse inconsistently; AD012 provenance/status cannot be preserved; a proposed new path is absent without explicit approval provenance; the historical generator output fails deterministic reconstruction; a path's current `final_owner` would require a semantic decision rather than mechanical derivation; or counts can only be made to match by trusting current AD014 cells. Specifically, keep `rd_managed_adoption.py` out of current approved-primary/final-owner output unless a later explicit decision restores a cohesive file-level owner after the false-OFF issue is resolved.

## Repository and proof limits

- Branch: `feature/main-mix-countdown-display`.
- HEAD: `3c692554074b27805419a9b0767133a1c8d78150`.
- Staged changes: 0. Worktree was already broadly dirty; 471 porcelain entries observed during this audit. Existing WIP was preserved.
- No tests run; this was a document/CSV/generator inspection, not implementation acceptance.
- No CSV or source generator changed. No node104, HA, ESP Native, network, firmware, service, device, or hardware operation. No secret values read or disclosed.
- Current path-by-path AD012/Git-status crosswalk for every later approval has not been independently materialized in this report; repository source bytes may also differ from HEAD because of pre-existing dirty WIP. Registry publication therefore remains HOLD pending a separate deterministic additive snapshot implementation/review.
- R7.2 route execution/ACK was not inspectable or claimed in this environment.
