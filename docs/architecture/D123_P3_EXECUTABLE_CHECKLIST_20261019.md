# D123 P3 preparation — stage effect endpoint checklist

Status: active P3 checklist; completed cuts and evidence are appended below.
Use the existing application, charge-stage, safety, and execution owners. Do not
add an owner or alter recipes, target thresholds, OVP/OCP, lease, or MAIN Guard.

## Inventory captured for next cut

### First bounded effect cut prepared after Sprint 05 (not implemented)

Move only the `AuthorityAction.ENTER_DESULFATION` effect currently applied by
`ManagedChargeController._apply_authoritative_decision` through
`_enter_desulfation` into the existing application/charge runtime orchestration.
The existing decision remains `runtime.charge.strategy.main_authority`'s
`decide_main_transition`; the migrated effect must produce the exact current
action dictionary (`log_event_end`, stage `Десульфатация`, `set_voltage`,
`set_current`, desulfation limits, `notify`, `log_event`) with the existing
reset, retry-count and timestamp semantics. Keep execution and verified commit
in the existing `application.execution_port`; do not call setters directly or
add an independent session writer. Characterize calls from both the existing
controller tick and production runtime before editing. If the application owner
cannot accept a single typed effect result without a parallel stage writer,
stop and record a blocker rather than moving partial mutations.

Required before this cut: trace P2d owner/capture gates green; exact action-key
and value parity, state/reset parity, same execution-port call count, OFF/ON
transaction failure and restart tests. This is a task definition only; no P3
source change was made in Sprint 05.

| Current controller mutation endpoint | Existing target boundary | Minimum characterization suites |
|---|---|---|
| `tick`, `_run_stage_scaffold_tick`, `_apply_authoritative_decision` | Existing application orchestration + charge decision/scaffold results | `test_charge_controller_authority`, `test_v3_main_authority_migration`, `test_v3_recovery_authority_migration`, full controller suite |
| `_enter_desulfation`, `_complete_desulfation_to_safe_wait`, `_advance_agm_step`, `_apply_recovery_safe_wait_authority` | Existing `runtime.charge.strategy.desulfation`, `recovery`, `recovery_safe_wait`; application transaction/commit | `test_desulfation_ownership_cutover`, `test_recovery_safe_wait_output_transaction`, AGM authority tests |
| `_enter_mix`, `_apply_final_safe_wait_authority`, `_handle_mix_stage_override` | Existing MIX/post-mix/final SAFE_WAIT decisions; application transaction/commit | `test_final_safe_wait_output_transaction`, `test_mix_active_timeout_integration`, `test_v3_mix_authority_migration` |
| `_enter_safe_wait_done` (removed Sprint 09); `_stop_and_diagnose`, cooling/storage/done transitions | `runtime.charge.runtime.final_safe_wait_entry` owns the typed MAIN/MIX entry effect; existing SAFE_WAIT, cooling, storage decisions and execution OFF/verified commit remain | `test_d123_p3_final_safe_wait_entry_effect`, `test_final_safe_wait_output_transaction`, `test_done_storage_restore`, cooling and output-off suites |
| `commit_verified_enable_transition`, `_handle_safe_wait_stage_override` | Existing `application.execution_port` verified transaction and commit boundary | START/output transaction suites; exact lease and actuator call-count contracts |
| `_apply_continuous_tail_hold` and production cooling pause mutation | Existing production policy/evidence and canonical session persistence extensions | `test_production_controller`, cooling restore and session atomic guard-binding suites |

## Sprint 31 — MIX authority dispatch ownership

- [x] Starting source pin: exact requested HEAD `5f5f2b42c9d14c820d2968f3381c6aae5b052db0`; preserved the existing unstaged MIX extraction found in the worktree and validated it as the single Sprint 31 source cut.
- [x] Move MIX evidence mirror application, `decide_mix_transition`, finish-hold effect construction/application, final SAFE_WAIT completion dispatch, and STOP_AND_DIAGNOSE dispatch from `_apply_authoritative_decision` into the existing `runtime.charge.runtime.mix_scaffold.apply_mix_authority_tick` owner.
- [x] Keep `_apply_authoritative_decision` as the sole caller for MIX authority. The runtime owner has no execution port, RD setter, or actuator API; action execution and verified transaction ownership remain in `application.execution_port`.
- [x] Preserve one decision call, existing decision/action keys and order, finish evidence and hold behavior, invalid identity fail-closed handling, and downstream timeout/SAFE_WAIT transaction paths; focused parity/failure/static guards pass.
- [x] Run focused tests, full Python 3.12 offline discovery, `compileall`, and `git diff --check`; exact evidence and limitations: `D123_SPRINT31_EVIDENCE_20261020.md`.
- [ ] Next gate: inspect one remaining controller-owned orchestration boundary around SAFE_WAIT or `_run_stage_scaffold_tick`; do not cross deferred Guard restore admission or split verified Storage/DONE save ordering. Manual and P4 remain outside this cut.

## Executable gates before each P3 edit

- [ ] Pin current HEAD and clean-tree state; append evidence, never rewrite prior
  sprint results.
- [ ] Capture the production caller and direct callers for each endpoint:

  ```bash
  rg -n "def (tick|_run_stage_scaffold_tick|_apply_authoritative_decision|_enter_desulfation|_complete_desulfation_to_safe_wait|_advance_agm_step|_apply_recovery_safe_wait_authority|_enter_mix|_apply_final_safe_wait_authority|_enter_safe_wait_done|_stop_and_diagnose|commit_verified_enable_transition)" charge_controller.py
  rg -n "\.(tick|commit_verified_enable_transition)\(" runtime application
  ```

- [ ] For each migrated path, retain exactly one decision caller and one
  `application.execution_port` physical transaction. Compare action keys,
  stage history, verified OFF/ON receipt, and persisted state before/after.
- [ ] Require fresh direct Native evidence under the repository preflight before
  any physical acceptance; source tests alone never assert physical PASS.
- [ ] Run focused suites for that exact stage and its OFF/restart/Guard failures,
  then the complete offline unittest suite on `/tmp/rd6018-d109-venv/bin/python`
  with only `TG_TOKEN=123456789:d123-offline-sprint03`, plus `compileall`.
- [ ] Commit one verified source cut and update the owner map/checklist. Leave
  untouched stages explicitly pending; no P3 completion claim from inventory.

## Sprint 22 — MIX completion dispatch

- [x] Starting point pinned: clean `08e7e8a4b8e7084d830f6e9dc79b4a85d66d7234`.
- [x] Move MIX hold-completion evidence logging and typed final SAFE_WAIT
  input/dispatch into the existing `runtime.charge.runtime.final_safe_wait_entry`
  owner. Keep storage target selection in the controller and keep invalid
  identity containment fail-closed.
- [x] Add parity, stale-identity failure and AST/no-physical-writer guards.
- [x] Run focused suites, full Python 3.12 offline discovery, compileall and
  `git diff --check`; see `D123_SPRINT22_EVIDENCE_20261019.md`.
- [ ] P2 Guard restore admission remains fail-closed/deferred. Continue with a
  separate bounded P3 owner cut; do not start P4 or claim convergence.

## Sprint 23 — MAIN completion dispatch

- [x] Starting point pinned: clean `67c670238c4370ab45bb83ab8604e47cdcdec51c`.
- [x] Move MAIN `COMPLETE_TO_SAFE_WAIT` typed input assembly and dispatch into
  the existing `runtime.charge.runtime.final_safe_wait_entry` owner. MAIN
  decision and controller `_storage_target()` selection remain in place;
  invalid identity still enters controller STOP_AND_DIAGNOSE containment.
- [x] Add profile target/action parity, stale identity rejection, and AST / no
  physical writer / single-dispatch guards.
- [x] Run focused suites, full Python 3.12 offline discovery, compileall and
  `git diff --check`; record exact results in Sprint 23 evidence.
- [x] Commit this single source cut and finish with a clean worktree.

## Sprint 24 — MAIN DESULFATION and MIX entry dispatch

- [x] Starting point pinned: clean `4662f54d4f0af722f9b96b246e83658d97df5a7a`.
- [x] Keep `decide_main_transition`, `_desulf_target(temp)`, `_mix_target(temp)`,
  and MIX protection-limit selection in the controller; move typed input and
  event-end assembly plus single application into the existing stage owners.
- [x] Add Ca/Ca, EFB and AGM target/action parity, pre-mutation failure, and AST
  single-dispatch/no-inline-input guards for both entries.
- [x] Run focused suites, full Python 3.12 offline discovery, compileall and
  `git diff --check`; record exact results in Sprint 24 evidence.
- [x] Commit this single source cut and finish with a clean worktree.

## Sprint 26 — verified Storage terminal persistence intent

- [x] Starting point pinned: clean `33382b6edd424876738896d81e3a48c58f2b7338`.
- [x] Replace `_done_transition_source_stage` mutable marker inference with an
  explicit `verified_storage_completion` argument at the canonical session
  save boundary, passed only by `FinalSafeWaitCompletionEffect` application.
- [x] Preserve persisted schema, restore admission, terminal fallback and
  execution-port receipt/transaction ordering; add static marker-removal and
  Storage/restore failure regression coverage.
- [x] Run focused/full Python 3.12 offline discovery, `compileall`, and diff
  check; see `D123_SPRINT26_EVIDENCE_20261019.md`.
- [x] Commit one source-only cut and finish with a clean worktree.

## Sprint 27 — broader terminal persistence ownership (blocked, documented)

- [x] Starting point pinned: clean `7f5e334d2d657b1c22528026fd7f1dafece162c8`.
- [x] Trace DONE saves from both the receipt-gated Storage completion effect
  and `STOP_AND_DIAGNOSE` into the canonical atomic writer and inspect restore
  admission/fallback.
- [x] Record the exact blocker: terminal snapshot serialization and restore
  normalization are shared canonical persistence responsibilities. Moving only
  Storage/DONE fields would split schema authority or change the verified
  completion's stage/save ordering; moving the whole serializer is not a
  bounded P3 cut and risks ordinary-session parity.
- [x] No source ownership was moved or deleted. Focused and full offline
  regression, compileall and diff-check results are in
  `D123_SPRINT27_EVIDENCE_20261019.md`.
- [ ] Next gate: characterize a transaction-shaped terminal persistence port
  used by both Storage completion and STOP_AND_DIAGNOSE, including injected
  writer failure and restart/restore parity. Keep the writer in
  `runtime.charge.persistence`; do not add a parallel serializer. Resume only
  when a cut can transfer terminal snapshot authority without changing the
  verified receipt -> stage edge -> canonical save ordering.

## Sprint 29 — SAFE_WAIT continuation restore ownership cut

- [x] Starting point pinned: clean `d1f710a251b59a6c5b53af019e082e033f216112`.
- [x] Read current writer, controller save/restore/continuation code, owner map,
  Sprint 28 evidence, and session/restore/Guard regressions.
- [x] Move the paired recovery/final SAFE_WAIT continuation reconstruction
  bodies into `runtime.charge.session_continuation_restore`; keep core restore
  admission and orchestration in their current owners. Both move together for
  typed/legacy continuation parity. See `D123_SPRINT29_EVIDENCE_20261020.md`.
- [x] Focused suite **49 PASS**, full Python 3.12 offline discovery
  **2,423 PASS / 3 skipped**, compileall and diff check PASS.
- [x] Commit source-only continuation restore ownership cut with clean tree.
- [ ] Next gate: characterize an ordinary session serialization request seam only if
  schema, extension, Guard, identity, and atomic writer authority remain whole.
  P2 Guard restore admission stays fail-closed/deferred. Manual/P4 remain
  untouched.

## Sprint 31 — MIX authority orchestration ownership

- [x] Manual independence audit: production Manual START and STOP remain on
  `ProductionManualUIRoute` / `ProductionManualSessionManager`; no active Manual
  state or recipe coupling remains in `ManagedChargeController`.
- [x] Move MIX evidence mirror, transition decision, finish-hold effect dispatch,
  MIX completion dispatch, and STOP_AND_DIAGNOSE dispatch from
  `_apply_authoritative_decision` into the existing
  `runtime.charge.runtime.mix_scaffold.apply_mix_authority_tick` owner.
- [x] Preserve MIX decision inputs, profile authority limit, action payloads,
  evidence fields/logs, completion target selection and fail-closed stale-session
  containment. The controller retains one guarded call after authoritative-stage
  validation; the existing application execution path remains unchanged.
- [x] Add/retarget parity, stale identity, owner dispatch, and no physical-writer
  guards; preserve MAIN completion and Guard/restore admission boundaries.
- [x] Full Python 3.12 offline unittest discovery with synthetic `TG_TOKEN`,
  compileall, and diff check recorded in `D123_SPRINT31_EVIDENCE_20261020.md`.
- [x] Commit one source-only cut with a clean worktree.
- [ ] Next gate: assess the remaining central `_apply_authoritative_decision`
  MAIN/SAFE_WAIT orchestration and tick evidence/trace glue for a bounded move
  into existing owners. Keep P2 MAIN Guard restore admission deferred/fail-closed;
  do not start P4.

## Sprint 32 — MAIN authority orchestration ownership

- [x] Pin clean baseline `b4c8440736fc5f9b5e1f447b22352dcddbac1db1`.
- [x] Move MAIN decision-input assembly and all five existing MAIN outcome
  dispatches from `_apply_authoritative_decision` into
  `runtime.charge.runtime.main_scaffold.apply_main_authority_tick`; retain the
  controller's stage admission and all existing typed effect/transaction owners.
- [x] Preserve decision values, target policy, action payloads, stage/session
  state, and invalid identity STOP_AND_DIAGNOSE containment. Add outcome parity,
  input, single-dispatch, and no-physical-writer tests.
- [x] Focused suite **38 PASS**; full Python 3.12 offline discovery
  **2,426 PASS / 3 skipped**; compileall and diff-check PASS.
- [x] Record exact source-only scope in `D123_SPRINT32_EVIDENCE_20261020.md`.
- [x] Commit this source cut and verify the resulting worktree is clean.
- [ ] Next gate: inspect remaining DESULFATION/recovery/final SAFE_WAIT routing
  and tick evidence/trace assembly for one bounded move. Preserve the deferred
  P2 MAIN Guard restore admission boundary; do not start P4.
