# P1-AD072 — START enable cancellation settlement decision
Date: 2026-11-15
Status: AUDIT ACCEPTED — cancellation containment remains OPEN; no implementation authorized.

## Verdict

**OPEN for the current START cancellation path.** AD051 closes host-side retransmission of a superseded ON when a later OFF is actually submitted through the same firmware Output owner. The current START path does not guarantee that cancellation submits that OFF. The Python coroutine can be cancelled after Native send, discard its receipt waiter, and unwind without any OFF compensation.

## AD042 disposition: PARTIALLY SUPERSEDED

Stale for the current default configuration:
- The claim that the configured production default has no request-correlated terminal receipt.
- The claim that HA REST timeout is the configured default Output transport.

Still current:
- START cancellation can leave the remote ON outcome unsettled.
- A Python cancellation is not remote cancellation.
- The current START cancellation path does not itself guarantee emergency OFF.
- A terminal OFF readback is not proof that another independent writer cannot later issue ON.

AD051's same-owner queue fence supersedes the narrower host-side retry/retransmission concern, subject to the configured connector and no alternate writer.

## Current path and proof

- `config/physical/connectors.yaml:3` defaults to `esp_direct`.
- `runtime/config/loader.py:76–87` permits non-empty `RD6018_CONNECTOR` to override that default. `ha_esp` remains an enabled alternative. The actual node/service environment was not inspected; therefore the deployed effective connector is not claimed.
- Default path: `HassClient.from_physical_config` → `ESPDirectConnector` → `ESPHomeTransport.command_output` → request-ID-correlated Native receipt → single firmware OutputOwner → dedicated R18 Modbus device.
- `esp128.py:498–548` sends a UUID request and waits for matching terminal receipt; `:551–553` removes the Python waiter/cache in `finally`, but does not cancel firmware work.
- `output_owner.cpp` distinguishes unsent `CANCELED` from sent `OUTCOME_UNCERTAIN`; FC06 ACK is only `ACKNOWLEDGED_WAITING_READBACK`; `APPLIED` follows matching one-shot FC03 R18 readback. The bounded receipt ring is RAM-only.
- Exact ESPHome 2026.8.2 queue evidence in AD048 and `UPSTREAM_SOURCE_SNAPSHOT_MANIFEST_20261113.md`: device-scoped silent retirement removes unsent frames and detaches callbacks/retries from sent in-flight shells; the shell occupies the single-response slot until response/timeout; replacement OFF is queued behind it. This is not address-wide and does not touch other device telemetry.

**Conditional inference:** with effective connector `esp_direct`, the one dedicated R18 owner, no alternate writer, and the pinned Modbus queue behavior, a subsequent same-owner OFF can fence host-side re-transmission of the earlier ON. A terminal OFF APPLIED receipt plus fresh R18 readback proves the owner's OFF command and observed R18 state. It does not independently prove proprietary RD6018 device processing semantics beyond the exact host queue source, nor exclude a later independent writer. If `RD6018_CONNECTOR=ha_esp`, the configured alternative uses HA REST and has no AD051 correlated receipt; AD042's transport concern remains for that configuration.

## Concrete current START gap

- `strict_guard.py:219–235` catches `Exception` around ON cleanup, not `asyncio.CancelledError`.
- `execution_port.py:281–306` catches only selected ordinary exceptions; cancellation propagates while the task-reentrant app lock unwinds.
- `start_transaction_service.py:431–461` sets `enable_attempted` and awaits enable, but its compensation is in `except Exception`; `CancelledError` bypasses it and no `request_emergency_off` is issued.
- `esp128.py:551–553` removes the Python waiter on cancellation; firmware command may still be active.
- The same-owner queue fence is therefore only used if some caller explicitly submits OFF. Current START cancellation does not guarantee that call.

There is a second coupled atomicity blocker: `start_transaction_service.py:354` calls `charge_controller.start()` before Output enable; `runtime/charge/lifecycle.py:83–85` clears the prior canonical session file during initialization. No typed durable replacement commit/readback is established before START success. Do not patch cancellation by simply clearing the controller/session: that would compound the existing old-session loss.

## Smallest safe next contract

Use the existing single owners only:
1. START cancellation after enable begins must submit emergency OFF through the existing `ExecutionPort.request_emergency_off` / same configured physical owner.
2. Await terminal OFF APPLIED plus matching fresh R18 readback; preserve fail-closed/quarantined state if OFF cannot be established.
3. Keep the previous canonical session intact until the new session has a typed durable commit/readback result; cancellation/failed START must not erase old Guard/interruption evidence.
4. Add focused fake tests for sent ON cancelled → same-owner OFF APPLIED, unsent ON → OFF, uncertain timeout → OFF without retry, and reconnect between ON/OFF. Do not add a queue, worker, lock, poller, token, auth mechanism or second Output owner.

**Implementation remains blocked** until the existing persistence owner exposes the required commit/readback contract from AD040/AD041. No partial ExecutionPort-only change is authorized because it would not cover cancellation after enable returns but before the START transaction commits.

## Verification and safety

AD072 was read-only. Tests listed in the report were **NOT RUN**. Existing receipt and queue tests do not execute Python task cancellation followed by same-owner OFF end-to-end. No source/test/CSV/config/firmware changes, no HA/ESP Native API/network, no hardware, no node104, no firmware build/flash, no deployment or service restart. No physical state is claimed. Branch/HEAD remain `feature/main-mix-countdown-display / 3c692554074b27805419a9b0767133a1c8d78150`; dirty WIP preserved. START and release remain HOLD.

## 2026-11-24 B878 implementation update

B878 selected and implemented the typed outcome boundary under the existing transaction owner, without changing the AD072 cancellation settlement sequence. Submitted-enable cancellation still shields and awaits the existing same-ExecutionPort OFF settlement before propagating `CancelledError`; fake tests exercise this path. This source/fake result does not prove ESP/firmware/device ordering or physical cancellation containment. AD072 remains OPEN for that acceptance, and P8 remains HOLD. See the B878 runbook/checkpoint entry for scope and evidence.
