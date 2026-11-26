# P1-AD076 — Session and canonical persistence function-group decisions
Date: 2026-11-15
Status: FUNCTION-GROUP OWNERS ACCEPTED; both target files remain NO FILE-LEVEL APPROVAL. No code movement.

## Whole-file decisions

| Module | Decision | Reason |
|---|---|---|
| runtime/charge/session.py | **NO FILE-LEVEL APPROVAL** | One file contains logical session model, trace identity, Guard recovery capabilities and Engine stage-history mutation. These are distinct existing departments. |
| runtime/charge/persistence.py | **NO FILE-LEVEL APPROVAL** | Canonical persistence is the dominant responsibility, but the same file also contains Safety admission predicates, terminal Engine semantics, Application/recovery retirement orchestration and a multi-owner restore coordinator. |

No source moves or new modules are approved. The decision is about primary ownership, not rejection of the existing implementation.

## Function-group owner decisions

### runtime/charge/session.py

| Function / class group | Accepted owner | Boundary |
|---|---|---|
| SessionStatus, SessionSnapshot, SessionManager | Sessions & Persistence | Pure logical session lifecycle model. SessionManager has no current production caller; direct tests only. It is not a second production state authority. |
| TraceIdentitySnapshot, new/project/restore/prepare/apply trace identity | Sessions & Persistence | Owns canonical trace identity values and host projection/application. It does not own Safety or stage policy. |
| RestoredSessionDocument | Sessions & Persistence | Immutable decoded-session boundary consumed by restore finalization. Persistence still owns the serialized schema. |
| GuardedRestoreCandidate and guarded activation permit issue/validation | Recovery & Ownership | Owns the guarded candidate and one-transaction restore activation capability bound to identity, document bytes, revision, current task and existing owner lock. |
| GuardedPhysicalResumePermit and issue/validation | Safety Authority | Owns the final physical-resume capability and Native evidence generation binding. Validation remains in ExecutionPort. |
| set_current_stage and stage-history normalization/restore/clear | Engine / Charge Stages | Owns stage transitions, transition reasons and bounded history; persistence calls the restore/clear operations but does not own the stage policy. |

### runtime/charge/persistence.py

| Function / class group | Accepted owner | Boundary |
|---|---|---|
| SESSION_FILE, read_canonical_session, clear_session_file, save_session, canonical AUTO schema | Sessions & Persistence | Single canonical document owner and sole writer. clear_session_file remains destructive and must not be used before a new START candidate commits. |
| atomic_session_write and complete_session_document in session_atomic.py | Sessions & Persistence | Existing one atomic writer/serializer. No parallel writer or sidecar is authorized. |
| mark_session_interrupted schema/write | Sessions & Persistence | Persistence owns bytes/schema and exact identity/hash update; Recovery & Ownership owns restart admission and fail-closed interpretation. |
| retire_controller_session tombstone write/readback | Sessions & Persistence | Persistence owns the durable tombstone and canonical file replacement; Application owns the operator clearance use case and supplies verified-OFF transaction identity. |
| managed_storage_ownership_proven | Safety Authority | Read-only persisted-state predicate used by ManagedRuntimeSafetyGuard to decide whether managed Storage may remain energized. Persistence supplies canonical data; Safety owns the admission rule. |
| paused_done_resume_is_authorized | Safety Authority / Recovery & Ownership | Admission policy for paused terminal-DONE resume; Application calls it but does not own the safety/recovery rule. |
| _set_done_outcome and terminal DONE semantic normalization | Engine / Charge Stages | Owns terminal completion kind/output intent semantics. Persistence owns the canonical serialization of the resulting state. |
| enrich_restored_session | Application | Coordinates the accepted restore finalization boundary; actual finalization remains in the already-approved restore_finalization.py Application owner. |
| restore_session | Sessions & Persistence (canonical restore coordinator) | Owns canonical read and restore sequencing only. It delegates admission to restore_admission, pure scalar/timeline projection to restore_projection, stage history/trace identity to session.py, Guard/native recipe validation to their existing owners, and finalization to restore_finalization. It does not own those delegated policies. |

The whole-file decision remains NO FILE-LEVEL APPROVAL because these function-group owners differ. Keep the existing public call graph; no mechanical extraction is approved by AD076.

## START replacement / cancellation boundary

The existing Sessions & Persistence owner can implement the missing typed canonical commit/readback result using the existing atomic_session_write primitive. This is not a new writer. The typed operation must:
- pin the exact prior canonical document bytes/hash and session identity;
- prepare a detached candidate without mutating/clearing the prior document;
- perform one replacement through the existing atomic writer;
- read back and classify COMMITTED, NOT_COMMITTED (exact old document retained), or OUTCOME_UNCERTAIN (neither exact old nor candidate can be proven);
- expose the result to the existing START Application use case; START success must depend on COMMITTED.

Routine save_session remains a periodic projection API; it currently returns None and catches/logs OSError. It cannot be treated as a commit receipt. Candidate projection is not a durable commit.

AD072 remains a separate execution blocker: the current START cancellation path does not guarantee same-owner emergency OFF when CancelledError unwinds. Persistence readback cannot settle Output. The final transaction must preserve the old canonical session until the new candidate commits and, on cancellation after enable begins, submit and await the existing ExecutionPort same-owner emergency OFF with terminal OFF APPLIED/R18 evidence. If OFF or commit is uncertain, retain quarantine/fail-closed state. No partial persistence-only or ExecutionPort-only fix is approved.

## Production call graph and bypass finding

- Save: charge_controller._save_session delegates to save_session; production callers include charge-session tick, MAIN Guard transaction, production lifecycle, completion/SAFE_WAIT/diagnostic runtime and restore finalization.
- Restore: charge_controller.try_restore_session delegates to restore_session; production callers include production lifecycle/runtime, startup recovery and operator pause.
- Retirement: OperatorRecoveryClearanceService → ControllerSessionRetirement → retire_controller_session.
- Interruption: existing recovery/lifecycle path uses mark_session_interrupted with exact prior hash/identity.
- Trace identity: charge controller START and MIX entry create/apply identity; restore projects/prepares/applies it.
- Guard permits: startup recovery issues; persistence validates activation; ExecutionPort validates physical-resume capability.

No reviewed session/persistence consumer directly invokes ESP/HA setters or the physical owner. START and guarded physical resume pass through the canonical ExecutionPort. Restore changes software session state only.

## Test evidence and limits

AD074 inspected the following; all NOT RUN:
- Logical lifecycle: test_phase7_0_domain_runtime.py, test_phase7_1_domain_runtime_parity.py.
- Trace identity/projection: test_recovery_trace_identity.py, test_modularization_pure_trace_projection.py, test_modularization_trace_projection_parity.py, test_modularization_trace_preapply_cutover.py.
- Stage history: test_d123_p2c_stage_history.py, test_modularization_stage_history_projection.py, test_modularization_restore_history_trace_contract.py, test_modularization_restore_stage_timeline.py.
- Guard permits: test_d070_guarded_restore_hold.py, test_d123_sprint57_guard_native_evidence.py, test_d123_sprint58_guarded_activation_architecture.py, test_d123_sprint59_guarded_physical_resume.py, test_session_atomic_guard_binding.py.
- Restore: test_modularization_auto_restore_admission.py, test_modularization_auto_restore_atomic_admission.py, test_modularization_auto_restore_projection.py, test_modularization_restore_finalization_contract.py, test_modularization_restore_continuation_failures.py.
- Interruption/retirement: test_modularization_auto_interruption_marker_ad039.py, test_d087_recovery_clearance_integration.py.
- Routine regression: test_production_controller.py, test_native_recipe_session_persistence.py, test_native_recipe_restore_parity.py, test_done_storage_restore.py, test_guarded_storage_terminal.py, test_v3_recovery_authority_migration.py, test_v3_mix_authority_migration.py, test_final_safe_wait_output_transaction.py.

Missing: full START transaction cut-point matrix for old-byte preservation, post-replace directory-fsync uncertainty/readback, exact old-vs-new classification, no destructive precommit clear, recipe-runner/canonical commit order, and cancelled sent-ON → same-owner OFF APPLIED/R18. Source/AST assertions are not behavioral transaction proof.

## Audit provenance and safety

AD074 was read-only, exit 0, no tests. The report exists at the exact launcher-supplied path .recipe-studio-local/REPORT_MOD_P1_AD074_SESSION_PERSISTENCE_OWNER_AUDIT_20261115.md (17,986 bytes). Its internal note that no -o path was visible is inaccurate: the outer launcher supplied that exact destination and captured the complete report there. No alternate report path was used.

No source/test/CSV/registry changes, no HA/ESP Native/network/hardware/firmware/node104/deployment. Output, Safety Lease and raw R16 remain outside this decision. Branch/HEAD unchanged; dirty WIP preserved; START/release HOLD.
