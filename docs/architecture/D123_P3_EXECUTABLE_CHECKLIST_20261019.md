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
