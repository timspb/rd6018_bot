# B1018 — finite source architecture closure assessment

Date: 2026-11-26
Run: `rd6018-b1018-20261126-r73-architecture-closure`
Branch: `codex/rd6018-b1018-architecture-closure-20261126`
Base/current code HEAD: `383d1613488062596d710cf97ad2c4778eea08dd`
Working tree at inspection start: clean.
Scope: source architecture and documentation review; no production source changes.

## Decision

**STOP the source-refactor treadmill.** This review found no material source
ownership defect requiring another split or a bounded source fix. The current
intended source boundary is sufficiently complete for this finite review; the
remaining release decision is gated by the physical and release evidence below.
This is not a claim of physical acceptance or proof that all 103 documentary
criteria are closed.

Ranked material source architecture gaps: **0**.

## Exact remaining P0–P9 criteria

The first canonical status/checklist block in
`docs/RD6018_MODULARIZATION_EXECUTION_PLAN_P0-P9_2026-11-17.md` contains six
unchecked criteria (97/103 complete). Historical appended templates and old
status blocks were excluded.

| Phase | Unchecked criterion | Evidence that could close it | Can close without physical action? |
|---|---|---|---|
| P3 | Confirm V/I programming/readback, ON/OFF, Native receipt, and causal evidence linkage. | Authorized target test record from the exact deployed source: command and readback sequence, fresh direct ESP Native callbacks/receipt and identity, measured V/I, R18, and event-to-command evidence linkage. Source/fake tests alone do not establish this. | No, as written; the required Native receipt and physical readback are observed at the target. |
| P3 | Separately pass the authorized R18/OPP/lease hardware gate. | Authorized bench evidence for actual R18, R16=3 OPP and unknown nonzero behavior, local 900 s lease/disarm, and verified OFF, with direct Native evidence. | No. |
| P3 | Do not touch node104/equipment before separate authorization and release gate. | Separate explicit authorization plus release-gate completion before any node/equipment action; then record the resulting boundary decision. This is a HOLD condition, not permission created by B1018. | The source-only review cannot satisfy or waive it. |
| P8 | Separately authorize and conduct physical acceptance. | A separately authorized physical acceptance record covering the accepted source/release candidate and required physical invariants. | No. |
| P8 | Consider node104 deployment only after release acceptance. | Release acceptance first, followed by a separately authorized deployment decision and the deployment runbook. The checkbox says “consider,” not “deploy.” | The prerequisite release acceptance includes physical acceptance; B1018 cannot close it. |
| P9 | Perform Git cleanup, commit, and push separately after classification and explicit destination review. | A reviewed exact path/diff classification and explicit destination authorization, followed by the separately scoped Git action. | Yes in principle; not in this run. The user explicitly prohibited staging, commit, push, and remote access. |

No checkbox changed. No extra regulatory, signature, cryptographic, or
security gate was inferred. R16 codes 1/2 remain observable/operator-managed;
R16=3 and unknown nonzero remain safety authorities, along with measured V/I,
temperature, R18 and the existing 900 s Native lease.

## Source review and ownership evidence

The review covered the production runtime and execution owner, START, recovery,
session persistence/restore, diagnostics, recipe/UI routes, Manual, recipe,
Telegram and AI/read-model seams, plus the current owner maps under
`docs/ownership/`.

| Area | Observed current boundary | Assessment |
|---|---|---|
| `runtime/production_runtime.py` | `data_logger()` at lines 709 onward owns the existing periodic observation/cycle orchestration. Its recovery and MAIN Guard transactions enter the same app-scoped `get_or_create_execution_port()` owner lock at lines 867–891 and 917–933. Unexpected-cycle emergency OFF goes through that ExecutionPort at lines 1050–1055. Runtime tasks/effects and compatibility façade remain a real runtime responsibility. | Large, but no second physical writer or independent loop/lock was demonstrated. A further split is not justified by size. |
| `application/execution_port.py` | The port binds one `GuardExecutionOwnerLock` (lines 267–278); normal operations are serialized by the existing decorator (36–44). Its enable, programming and OFF methods delegate to the composed safety execution owner. The app-scoped singleton helper is at lines 659–681. | Shared owner/lock is intentional and consistent across inspected START, recovery, controller action and Guard paths; do not add another port/lock. |
| `application/start_transaction_service.py` | `start_profile_transactional_result()` is the one lock-serialized START transaction (170–188). Its ordered body owns pending envelope/readback, prior-session/Guard retirement, preflight/effects, enable, evidence, commit/rollback and containment through line 707; line 710 is a compatibility wrapper. | Roughly 712 LOC reflects one atomic transaction with real failure cuts. No safe cohesive sub-owner or duplicated physical authority was evidenced; LOC alone is not a defect. |
| Recovery and restore | `SessionRecoveryService.run_cycle()` receives a fresh observation and caller-held owner lock; it returns ordered effects and uses the existing ExecutionPort (module contract lines 1–6, cycle lines 106–145). Production call is at `runtime/production_runtime.py:869–891`. `runtime/charge/session_restore.py::restore_session` owns snapshot admission/application; persistence re-exports it. | Distinct startup snapshot restore and live link recovery responsibilities remain separated. Deferred imports at recovery lines 160–168 are function-local dependencies, not demonstrated eager cycles. |
| Persistence | `runtime/charge/session_document_projection.py::project_session_document` is a candidate projection. `runtime/charge/session_atomic.py::atomic_session_write`, `compare_replace_session`, and `compare_delete_session` own canonical atomic/CAS writes. `persistence.py::save_session` and `start_pending.py` use those same primitives and START_PENDING fence. | Multiple callers participate in one writer contract; no second mutable persistence store or writer owner was found. |
| Diagnostics and signal projections | `runtime/charge/diagnostics.py` updates diagnostic context/assessment and applies a read-side HV veto; signal snapshots are in `runtime/charge/evidence/signal_diagnostic_snapshot.py`. The module documents no actuator write or charge-transition authority (lines 1–6). | Diagnostic state is owned diagnostic state; it is not evidence of duplicated charge or physical authority. No split indicated. |
| Recipe/UI/Manual/Telegram | `runtime/ui/telegram/recipe_buttons.py` (22–37) composes focused native draft/catalog/user/step/START route owners. START recipe selection only updates the existing pending START selection (`start_recipe_selection_buttons.py:64–139`); catalog commands explicitly state library recipes are not started through that UI (`recipes.py:21–32`). Telegram application routes submit typed intents; UI code inspected does not issue actuator calls. Manual physical interaction uses the existing Manual execution boundary/ExecutionPort, not Telegram. | Several route owners match distinct features and callbacks. No duplicate panel lifecycle or physical/write bypass was found. |
| AI/context | Operator read projections expose AI context through lazy compatibility exports in `application/operator_snapshot_provider.py`; the AI path is read-model/presentation context. | No AI-owned charge decision, session write or physical effect was found. |

No material duplicate mutable state, physical execution outside the sole
ExecutionPort, dynamic import cycle, cross-layer activation defect, second
active control loop, or UI write to unrelated domain persistence was established
in the inspected current production graph. This is a bounded source review, not
a claim that every historical inventory statement remains current.

## Source readiness, repository hygiene, and external status

- `git status --short --branch`: clean at review start; current branch is the
  B1018 work branch and HEAD equals the exact user-specified base.
- Tracked-path name scan for private credential/secret/config artifacts found
  only `config/secrets/README.md` and `esphome/secrets.example.yaml`; contents
  were not read. No private secret was accessed.
- Per task context, draft PR #182 contains B1002–B1017; CI #2242 and ESPHome
  dummy source build #161 are running. They were not queried, and their current
  results are not claimed here. No remote/local-origin comparison was made.
- Source architecture decision does not infer that P3/P8 hardware/release gates
  passed. Node104 status and deployment state were not queried.

## Finite next actions

1. Let the task-supplied CI #2242 and dummy source build #161 finish through
   their existing controller/launcher route; inspect results only on the
   appropriate subsequent controller review. Do not treat dummy compilation as
   physical acceptance.
2. If a source change is still proposed, require a newly demonstrated concrete
   ownership defect and bounded owner-preserving fix before starting another
   refactor. No such change is authorized by this assessment.
3. Keep P3/P8 HOLD until separate authorization and the evidence in the table
   exists. Consider node104 deployment only after accepted release/physical
   gates.
4. Handle P9 Git classification/destination review and any commit/push only in
   a separately authorized task.

Verification in this task: source inspection and tracked-path inventory only;
no tests added or run, no full CI, no AST/test harness run. `git diff --check`
is run for the documentation update.


## 2026-11-26 — B1018 independent controller acceptance and GitHub CI #2242 follow-up
R7.3 completion for run rd6018-b1018-20261126-r73-architecture-closure (event d6d7ab501ad44a3cb49081e3299d6b95) was received and server own-chat inspector ACK attempt_count=1. Source-only audit reviewed current production/owner graph and first canonical P0-P9 checklist: exactly six unchecked items remain (P3 three, P8 two, P9 one); no material additional production source ownership defect was demonstrated. Source normalization at the intended owner separation is sufficiently complete for this bounded review; STOP further cosmetic file splitting. Do NOT claim physical/release acceptance: P0-P9 stays 97/103, P3/P8/P9 HOLD.
Current feature HEAD 383d161 GitHub CI #2242 (run 45805720942) actually completed FAILURE in Python 3.10/3.11/3.12: 4067 tests each, exactly 5 FAIL and 2 ERROR per job, with the SAME seven stale D123 architecture test source-location assumptions after B1017 moved the real restore_session into runtime/charge/session_restore.py. No production source error or safety-policy failure was established by these results. ESPHome dummy-secrets source build #161 run 45805720846 SUCCESS, no flash.
Controller inspected all three GitHub job logs and fixed precisely seven stale tests across six files: tests/test_d123_sprint55b_architecture.py, test_d123_sprint55c_architecture.py, test_d123_p2c_stage_history.py, test_d123_p4_recipe_target_policy.py, test_d123_sprint58_guarded_activation_architecture.py, test_d123_sprint60_source_release.py. The updated contracts check the ORIGINAL safety invariants on the actual restore owner: Guard check before first host mutation, exact one restore_session definition, persistence direct reexport with identical object identity, restore_stage_history path, single canonical writer, absence of physical output methods, and startup/continuation order. No tests were removed or weakened and NO production source was changed. Independent normal HOME-PC WSL Python3.12 project venv, inert process-local TG_TOKEN and PYTHONPATH=.:tests:tools: ten-module cohort including all seven previously failing contracts, D123 Sprint30, guarded restore, restore finalization and production entrypoint **69/69 PASS exit0 (4.794s)**, scoped py_compile and git diff --check PASS. This is source/test correction, not current-head full CI acceptance. The test/docs-only correction is to be committed and fast-forward pushed ONLY to existing Draft PR #182, then its own GitHub CI checked before marking code green. This is NOT permission to deploy, flash, operate RD6018, or close physical gates.
