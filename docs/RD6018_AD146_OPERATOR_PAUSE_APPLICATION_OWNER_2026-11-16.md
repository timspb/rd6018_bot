# RD6018 AD-146 — Operator Pause Application transaction owner

Date: 2026-11-16  
Status: **APPLICATION OWNER APPROVED WITH TRANSACTIONAL HOLD ITEMS**  
Scope: source ownership audit only; no production-source change and no physical acceptance.

## Decision

Approve \`application/operator_pause_use_case.py\` as the sole Application owner for the Operator Pause/Resume transaction. The module owns orchestration of the existing pause/resume sequence, not persistence, charge-session state, Safety, physical execution, or HMI routing.

This closes the remaining AD069 file-level ownership question for this module. It does **not** certify the transaction for production/release: three existing failure semantics remain unresolved and require a separate narrowly scoped decision before deployment.

## Ownership map

- **Application — \`application/operator_pause_use_case.py\`:** pause/resume transaction ordering; pause/resume eligibility decisions; composition of the existing state and execution owners; one transaction under the canonical app execution lock.
- **Execution/Safety — app-scoped \`ExecutionPort\`:** all live reads; verified OFF/ON; V/I writes; managed Safety read path and actuator authority. The use case captures one port and does not use raw HassClient reads.
- **Execution serialization — \`GuardExecutionOwnerLock\`:** one canonical app-scoped, task-reentrant lock around the complete transaction. Emergency OFF remains the separate preemptive route.
- **Operator pause persistence — \`runtime/operator/pause_state.py\`:** the sole owner of \`operator_pause_state.json\` and its one-field schema. \`runtime/production_runtime.py\` holds the one state instance and exposes thin compatibility wrappers.
- **Charge session/engine — existing ChargeController:** owns charge-session save/restore and active-clock shifting. The use case calls the existing controller methods; it does not own controller state or clock implementation.
- **HMI/intent — \`operator_hmi.py\` + \`application/pause_command.py\`:** permission/cooldown/chat metadata, typed-intent validation/routing, callback acknowledgement and one call to the preserved runtime handler. No duplicate pause execution.

No new manager, state store, persistence file, timer, lease, lock, dispatcher, router, physical adapter or Safety gate is justified.

## Preserved transaction ordering

Pause:
1. Acquire the canonical app execution lock and capture one ExecutionPort.
2. Read through ExecutionPort.
3. If Output is ON, request verified OFF.
4. Read back; do not save/arm pause unless Output is confirmed OFF.
5. Save the existing charge session.
6. Set and persist the one existing pause timestamp.
7. Emit the existing event.

Resume:
1. Same lock and port; fresh read.
2. If Output is unexpectedly ON, request verified OFF and confirm readback.
3. Apply existing temperature/input guards and existing DONE restore authorization.
4. Restore the existing session only through ChargeController.
5. SAFE_WAIT shifts active clocks and clears pause without V/I programming or Output ON.
6. Normal resume programs existing V/I targets, requests verified ON, and only after success shifts clocks and clears pause.
7. Preserve existing event/result strings.

AD130's Safety read-path fix and whole-transaction lock remain intact. Emergency OFF remains outside the normal owner lock.

## Existing transactional HOLD findings

These are source-observed gaps, not newly introduced by AD146. They prevent production/release acceptance until separately resolved:

1. **Setpoint write results are ignored.** \`ExecutionPort.program_voltage()\` and \`program_current()\` return booleans. The use case currently awaits both but does not inspect either result before calling \`request_verified_on()\`. A rejected V or I write can therefore be followed by an Output ON request. Existing fake ports also do not model rejected writes. This is the highest-priority follow-up.
2. **Pause sidecar persistence is best-effort without a receipt.** \`OperatorPauseState.save()\` catches \`OSError\`, logs and returns \`None\`; the use case treats the pause as persisted regardless. A disk failure can leave in-memory pause active but no durable pause timestamp for startup recovery. Existing owner tests prove atomic replace/fsync on success, not failure propagation/transaction handling.
3. **Cancellation contract is not specified or tested.** \`toggle_operator_pause()\` has no explicit \`CancelledError\` compensation/finalization policy. Cancellation releases the async owner lock, but a cancellation between physical/state steps can leave a partial transaction. AD130 did not define or validate a cancellation compensation contract; do not claim that it did.

AD146 does not change these behaviors. Follow-up AD147 must define the minimal fail-closed result/compensation policy using the existing owners, without creating a new lock or transaction manager.

## Regression evidence

Corrected Windows project \`.venv\` cohort: **213 passed, 52 subtests passed across 21 modules**. Includes Operator Pause baseline/cutover/state owner/use case, legacy runtime callback, HMI/dashboard/intent, GuardExecutionOwnerLock, startup authority/recovery, START transaction, DONE restore, Hands-Off retirement/read-model behavior and runtime namespace contracts.

\`py_compile\`: PASS for the four inspected owner/entrypoint files.  
Scoped \`git diff --check\`: PASS.  
Six pre-existing \`SyntaxWarning\` messages in \`test_runtime_app_namespace_contract.py\` fixtures; no test failures.

The earlier attempted command named a nonexistent \`tests/test_operator_read_source.py\`; it executed no tests and is superseded by the corrected 21-module run above.

## Repository and safety

Branch \`feature/main-mix-countdown-display\`; HEAD remains \`3c692554074b27805419a9b0767133a1c8d78150\`; staged=0. No source edits were made for AD146. All existing WIP preserved; no commit/push/reset/checkout/stash/clean.

No node104 query or action. No HA, ESP Native, firmware, OTA, service, hardware or RD6018 Output action. 900-second Edge Safety Lease unchanged. Existing production/release/physical acceptance remain HOLD.

## Next — P1-AD147

Implement and test only the three transactional gaps above:
- reject resume before Output ON if either V/I write returns false; keep pause active and clocks unchanged;
- define a durable pause-save success/failure result without introducing a second persistence owner/file; do not claim pause persisted when save failed;
- define explicit cancellation-safe handling for the existing sequence, preserving emergency OFF preemption and canonical owner lock, with no duplicate lock or broad transaction framework.

Add fault-injection tests at every await boundary, especially after verified OFF, after session save, after pause timestamp assignment/save, after V write, after I write, after verified ON and before clock shift/clear. Preserve SAFE_WAIT no-ON behavior and existing successful ordering. Source/fake only; no physical acceptance.
