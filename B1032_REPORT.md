# B1032 — Shared Output ON receipt result

- **Run:** `rd6018-b1032-20261126-r73-shared-on-receipt`
- **Worktree:** `/mnt/e/CODEX/My_Local/RD6018_B1032_WORK/shared-on-receipt`
- **Branch / HEAD:** `codex/rd6018-b1032-shared-on-receipt-20261126` / `b9b662e7bc3b03fd3b638a2c40c447a9afbd7454`
- **Outcome:** **SOURCE HOLD — no production code changed.** The exact receipt propagation could not be proven without changing the existing guarded ON call chain in a way that risks duplicating or bypassing its owners. No physical PASS is claimed.

## Inspection and decision

The physical transport already creates an immutable `OutputCommandReceipt` from the correlated ESP Native terminal callback. Current production paths reduce it before it can be observed:

1. `ESPHomeTransport.command_output(True)` converts the receipt to a decoded dictionary.
2. `ESPDirectConnector.enable_output()` awaits that method and returns `None`.
3. `HassClient.turn_on()` discards backend return values and preserves the bool API; HA102 only returns the service-call bool and cannot provide a typed Native receipt.
4. `RuntimeSafetyGuard.turn_on()` consumes `_raw_turn_on` as bool, then performs live telemetry/envelope checks and existing OFF containment.
5. `StrictRuntimeSafetyGuard.turn_on()` wraps that operation with lease arm and cleanup/containment. `ManagedRuntimeSafetyGuard.turn_on()` adds managed temperature-integrity authorization and latch handling.
6. `ExecutionPort.request_verified_on()` preserves its legacy bool contract. The other production ON route, `ExecutionPort.enable()`, invokes `SafeOutputCoordinator`, which does its own setpoint programming, guarded `turn_on`, post-ON final readback, and verified-OFF containment on rejection.

A receipt obtained directly from `command_output_with_receipt()` would be evidence from a second ON invocation and is forbidden. Returning a tuple or a truthy wrapper from existing guard methods would change legacy semantics. Adding a separate receipt-aware guarded ON implementation would duplicate the Runtime/Strict/Managed guard logic and its containment ordering. A shared mutable “last receipt” or long-lived cache would not prove per-invocation identity. Therefore no production patch was made.

The present `test_b1030_on_receipt_boundary` confirms the reductions and the public bool/MRO boundary. It does not yet contain a fixture that runs one receipt-bearing fake command through the complete Managed → Strict → Runtime → SafeOutputCoordinator → ExecutionPort path and proves receipt invisibility until final acceptance.

## Smallest next executable source cut

Make the existing `ExecutionPort.enable()` / `SafeOutputCoordinator.enable()` transaction the only receipt-observation boundary. Extend the *same invocation* with a transaction-local optional receipt sink/capture passed down through the existing call chain; do not add a second ON API or a cached “last receipt.” Preserve all existing `turn_on()` bool returns and let HA102 produce no receipt. The selected ESP direct path should use `command_output_with_receipt(True)` exactly once, while legacy callers still use the bool behavior. The receipt candidate must remain private to the in-flight transaction until coordinator final readback and all enclosing Managed/Strict/Runtime checks accept. False, exception, guard rejection, or final-readback rejection must expose no receipt and must preserve the existing exact OFF containment. Keep existing ExecutionPort serialization, lease/recovery/HANDS_OFF/adopted gates, and OVP/OCP observation-only policy.

Before implementing this cut, add a bounded fake fixture whose one ON command returns a unique immutable receipt and whose call log makes every physical command visible. It must exercise:

- exact object identity from the single ON invocation through the accepted result; no receipt on false, exception, lease/guard rejection, or post-ON readback rejection;
- one raw ON invocation, unchanged legacy bool parity, and existing OFF containment on post-ON rejection;
- no receipt reuse across two invocations and no receipt synthesized for HA102;
- no ON command on recovery quarantine, HANDS_OFF/autonomous, or adopted-live/MIX authority rejection;
- no automatic OVP/OCP threshold reads/writes or OVP/OCP-based rejection.

Then implement only the minimal carrier needed by that fixture, without duplicating any guard method. If the call-chain carrier requires a second guard route or changes the guard order, keep this task HOLD and revise the contract instead of adding that route.

## Verification

Using `/home/home-pc/.venvs/pcp-test/bin/python`, inert test token, and `PYTHONPATH=.:tests:tools`:

- `tests.test_b1030_on_receipt_boundary`
- `tests.test_b1024_native_phase_evidence`
- `tests.test_execution_port_policy_boundary`
- `tests.test_managed_runtime_safety`
- **65/65 PASS** (0.912 s).
- Targeted `py_compile` for transport, connector, HassClient, Runtime/Strict/Managed guards, ExecutionPort and SafeOutputCoordinator: PASS.
- `git diff --check`: PASS.

No full suite was run. No RD hardware, node104, ESP/HA, Output/setpoints, firmware, service, deployment, network, GitHub, stage/commit/push, or original dirty worktree was touched. No runbook/checkpoint/master/handoff document was modified; this is a worker report for controller reconciliation. R7.3 completion is left to the launcher.
