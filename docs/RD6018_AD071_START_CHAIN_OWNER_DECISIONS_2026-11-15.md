# P1-AD071 — START chain owner decisions
Date: 2026-11-15
Status: PARTIAL ACCEPTANCE — three Application owners accepted; START transaction service remains unapproved.

## Decisions

| Module | Primary owner | Decision |
|---|---|---|
| `application/start_transaction_service.py` | NO FILE-LEVEL APPROVAL | HOLD — explicit START orchestration crosses controller lifecycle, Guard retirement, ExecutionPort enable/compensation, recipe-runner persistence and canonical session replacement without an observable commit result |
| `application/start_transaction_runner.py` | Application | APPROVED as-is for the existing transaction-input → V2 event/pending adapter and delegation to the single START service |
| `application/start_transaction_adapter.py` | Application | APPROVED as-is for data-only approved-plan preparation and typed outcome normalization; no physical or persistence authority |
| `application/charge_session_tick.py` | Application | APPROVED as-is for the single automatic session tick orchestration and data-only action batch |
| `application/main_guard_transaction.py` | Physical Execution | ALREADY APPROVED by AD056; reaffirmed, not a new approval |

## Evidence and owner boundaries

### Application — StartTransactionRunner
Production chain: `ProductionStartRouteAdapter.submit` → `ProductionStartExecutionPort.submit_active` → `ProductionStartRunner.execute_async` → `StartTransactionRunner.__call__` → `start_profile_transactional`. The runner maps immutable transaction input to the existing V2 event/pending objects and delegates to the existing transaction owner. It has no controller, physical adapter or persistence writer. Application is the single coherent owner.

**Known contract defect retained:** the runner currently reduces the service result to `started` and a reason. It does not propagate `output_off_confirmed`, `output_off_unconfirmed`, or session-containment distinctions into `StartTransactionOutcome`; the downstream adapter therefore cannot normalize the real production compensation result. This does not change the owner assignment and is not fixed by AD071.

### Application — StartTransactionAdapter
The adapter converts an approved preflight plan into immutable transaction data and normalizes the typed outcome into execution status/rollback state. It is data-only, fail-closed, and does not execute production I/O. Application is the owner. Its typed rollback vocabulary must remain aligned with the real runner outcome; do not add a second execution path.

### Application — charge_session_tick
The sole production orchestration caller is `runtime/production_runtime.py` (the existing active-session tick). It sequences recipe observation, existing charge-stage policy, Telemetry evidence, MAIN authority, existing trace/persistence calls and returns a data-only action batch for the production loop to apply through the ExecutionPort. The EFB plateau observer remains Telemetry; MAIN transition selection remains Engine / Charge Stages; Safety veto and physical effect remain their existing owners. The tick does not become a second Output writer.

**Known sequencing limitation retained:** the tick can persist a state transition before the later production action batch is applied; `save_session()` suppresses writer `OSError` and returns no commit result. This is a Sessions & Persistence contract gap and an Application sequencing concern, not a reason to assign the tick to Persistence or Physical Execution. No atomic state/effect guarantee is claimed.

### NO FILE-LEVEL APPROVAL — start_transaction_service
The service currently combines several materially different responsibilities: explicit START validation and sequencing; prior MAIN Guard retirement checks; controller/session initialization; initial PREP/MAIN target selection; physical enable through ExecutionPort; failed-start OFF compensation; recipe runner persistence; and operator success publication. It also initializes controller state through a lifecycle path that clears the canonical session file before a durable replacement exists. It has no synchronous canonical AUTO-session commit/readback before reporting START success.

The module must remain pending until the existing single persistence writer exposes a typed commit/readback result and the existing execution owner provides a proven cancellation/settlement contract. Do not split it speculatively or add a new writer/executor.

### Physical Execution — main_guard_transaction
AD056 already assigns this transaction module to Physical Execution. It performs the verified MAIN Guard write/checkpoint/compensation sequence only through the existing ExecutionPort and delegates canonical persistence to its existing checkpoint owner. AD070 confirms that this must not be broadened into START session ownership.

## START atomicity and cancellation status

AD040/AD041 remain valid for canonical persistence: controller initialization currently clears prior canonical state; `save_session()` has no commit result and suppresses `OSError`; post-`os.replace` uncertainty requires exact readback; disk-only unretired Guard evidence must not be silently dropped.

**AD070 correction after independent source review:** AD042's pre-AD051 statement that the production Output path has no command-correlated receipt is stale for the current configured connector. `config/physical/connectors.yaml` selects `esp_direct`; `HassClient.from_physical_config()` composes `ESPDirectConnector`; `ESPDirectConnector.enable_output()` calls `ESPHomeTransport.command_output(True)`; the transport sends a unique request ID and waits for the existing Native TextSensor receipt; the firmware Output owner distinguishes `CANCELED` (not sent) from `OUTCOME_UNCERTAIN` (already sent), disables retry, and serializes replacement work behind the in-flight shell. The same owner also requires one-shot R18 readback before `APPLIED`.

This means the old HA REST timeout is not the configured production default. However, the new receipt/queue contract has **not yet been shown to prove cancellation quiescence end-to-end**: the Python `command_output()` finally block removes its waiter on cancellation, and the focused tests do not exercise cancellation during a sent ON followed by emergency OFF and a terminal OFF receipt. Source/contract tests do not prove actual RD6018 serial/device ordering under the in-flight timeout case. Therefore cancellation settlement remains **NOT PROVEN**, but the AD042 rationale must be revalidated against AD051 rather than repeated unchanged.

Next narrow audit: AD072 must inspect the complete current default path, the firmware device-scoped queue semantics, cancellation at every Python await point, and whether a same-owner terminal OFF receipt can prove that no earlier ON can later be applied. Report only; no code/test/hardware changes.

## Verification and limits

AD070 was report-only and ran no tests. Its recommended test inventory is retained in `.recipe-studio-local/REPORT_MOD_P1_AD070_START_TRANSACTION_AUDIT_20261115.md`; all tests listed there remain **not run in AD070**. Relevant existing suites include `test_start_transaction_service.py`, `test_start_transaction_adapter.py`, `test_production_start_runner.py`, `test_esp_output_command_receipt.py`, `test_rd6018_output_owner_contract.py`, and `test_guard_execution_owner_lock.py`.

No source or test edits, no registry/CSV rewrite, no HA/ESP Native request, no physical action, no firmware/OTA, no service restart, no node104 or deployment. START and release remain HOLD. Preserve all dirty WIP; no stage/reset/clean/stash/checkout/commit/push.


## Additional source finding — cancellation is not automatically compensated

Independent current-source trace found a concrete gap separate from the stale HA REST premise:
- `runtime/safety/strict_guard.py:219-235` catches `Exception` around the ON call, not `asyncio.CancelledError`; cancellation bypasses its existing raw-state check/OFF containment.
- `application/execution_port.py:281-306` catches only `AttributeError/RuntimeError/TypeError/ValueError`; cancellation propagates through the port while the task-reentrant app lock unwinds.
- `application/start_transaction_service.py:431-447` catches `Exception` around `ExecutionPort.enable`; it does not issue `request_emergency_off` on task cancellation. Its helper `_confirm_failed_start_is_off` is reached only through the ordinary Exception path.
- `runtime/physical/transports/esp128.py:551-553` removes the Python receipt waiter/cache in `finally`; it does not cancel the already-sent firmware request or dispatch OFF.

Therefore same-owner queue serialization is useful **only after a new OFF request is actually issued**. The current START cancellation path does not itself issue that OFF. If cancellation is delivered after Native send and before receipt, the caller can unwind without waiting for the correlated receipt and without invoking the queue-fencing OFF. This remains an OPEN cancellation-containment gap regardless of whether the lower Modbus queue could safely serialize an explicit OFF. AD072 must retain this as a distinct finding. No implementation/test change.

## 2026-11-24 B878 correction — typed outcome boundary selected

The architect selected B876 option B and authorized the bounded B878 source/fake implementation: keep the single existing `start_profile_transactional_result` transaction as typed, retain `start_profile_transactional` as a bool compatibility wrapper over that same implementation, and have production `StartTransactionRunner` consume `StartTransactionOutcome` directly. `StartPersistenceStatus` reports only existing operation/readback evidence. The B878 evidence is recorded in the current runbook/checkpoint. This supersedes the earlier unresolved A/B contract-choice paragraph above, but it does not promote the whole `start_transaction_service` file to AD071-approved: other orchestration/owner-boundary review and production/physical acceptance remain open. No second writer, transaction, output owner, or lease path was added.
