# P1-AD089 — Same-owner cancellation fence decision
Date: 2026-11-15
Status: ACCEPTED AS CONDITIONAL FIRMWARE CONTRACT; START SETTLEMENT REMAINS OPEN.

## Accepted finding

AD088 is accepted. The AD051 firmware OutputOwner plus retained exact ESPHome 2026.8.2 Modbus hub queue provides a conditional host-side late-retransmission fence:
- Unsent ON is retired as CANCELED and cannot later be transmitted by that owner.
- Sent ON is marked OUTCOME_UNCERTAIN and its in-flight WAITING shell is silently retired with device=nullptr/pending=0. The hub retains the response slot until response/timeout; the retired shell has no device callback and cannot trigger owner retry. A later OFF from the same OutputOwner waits for the slot, then FC06 ACK + FC03 R18 readback must match before OFF/APPLIED.
- OFF/APPLIED therefore fences the earlier owner's ON from later host retransmission, under one OutputOwner, one powersupply hub/device, one R18 writer, exact pinned queue implementation and normal RD6018 serial request/response ordering.

This is not proof that ON never briefly applied before OFF, not a guarantee against another writer/future write/restart, not physical acceptance, and not a claim about proprietary PSU behavior outside source exchanges. The retained firmware snapshot is not proof of the currently flashed target binary.

## Current production gap

START's current Exception compensation does not catch asyncio.CancelledError. Cancellation of ESPHomeTransport.command_output clears the Python waiter/cache but does not cancel/settle a Native action already delivered. Therefore the conditional firmware fence is not invoked automatically by START cancellation.

The current transport receipt is lost at ESPDirectConnector/HassClient (None/bool); RuntimeSafetyGuard may return generic OFF bool from fresh live heartbeat even if the actuator command returned false. Existing ExecutionPort.VerifiedOffEvidence is fresh direct Native OFF readback but is not bound to a specific firmware OFF request ID/APPLIED receipt. ha_esp alternative connector has no AD051 typed receipt. Effective deployed connector is not known: RD6018_CONNECTOR overrides YAML default esp_direct.

## Required next architecture contract

Use only existing owners:
1. START Application service catches cancellation after enable begins, retains canonical prior session and awaits settlement before re-raising original CancelledError.
2. Existing ExecutionPort.request_emergency_off remains the liveness route (app owner lock bypass), and existing ManagedRuntimeSafetyGuard/_off_lock remains the single Safety/physical owner. Do not switch to the lock-taking normal OFF path merely to obtain evidence.
3. Extend the existing physical result propagation chain so exact ESPDirectConnector command_output(False) terminal receipt (request ID, APPLIED, target, observed R18) is preserved through HassClient and Managed guard/ExecutionPort. Pair it with a fresh direct Native SensorState R18=0 callback whose timestamp is after terminal OFF completion. Preserve ordinary bool API compatibility if existing callers depend on it. Do not fabricate receipts at upper layers.
4. If effective connector is ha_esp, AD051 receipt requirement is unavailable; fail closed for this settlement contract until a matching typed contract is deliberately implemented. Do not silently treat REST bool as APPLIED.
5. A second Task.cancel during settlement must not cancel/restart the same child settlement or duplicate OFF. Shield one child settlement task, continue awaiting that same task through repeated outer cancellation, then propagate the original cancellation after terminal result. Settlement failure retains Safety OFF-unconfirmed/quarantine and prior canonical session. Forced process/loop termination remains uncertain.
6. AD040/AD041/AD076 canonical START replacement/commit/readback is a separate blocker and must be solved before an isolated cancellation patch is considered complete.

No firmware queue redesign indicated by AD088. No implementation authorized by this decision alone; next step is a dedicated source-backed function-group/API design and exact acceptance tests. Do not patch until the typed result chain and canonical persistence transaction are both understood as one coherent START boundary.

## Evidence and limits

Full report: .recipe-studio-local/REPORT_MOD_P1_AD088_SAME_OWNER_CANCELLATION_FENCE_AUDIT_20261115_FULL.md. AD088 read current dirty working tree and retained upstream source snapshot; no tests, compile or lint run. No source/test/docs/firmware changes during audit. No HA/ESP Native/hardware/physical/deployment/node104 activity.

Branch feature/main-mix-countdown-display, HEAD 3c692554074b27805419a9b0767133a1c8d78150; all WIP preserved. START/release/deployment/physical acceptance HOLD.
