# B1034 acceptance — task-local ON receipt

**Run:** `rd6018-b1034-20261126-r73-tasklocal-receipt`
**Base:** `2d4fbd1d1235251215c5dceeeba07ef3fd69879e`
**Scope:** source and fake tests only

## Boundary implemented

The existing typed receipt is observed inside `ESPHomeTransport.command_output()`
after its single call to `command_output_with_receipt(enabled)`. For ON, the
observer receives the exact immutable object and the transport continues to
return the original decoded dictionary. OFF is not captured. HA102 follows its
existing REST path and cannot produce a Native receipt.

`ExecutionPort.enable()` establishes and resets a new `ContextVar` observation
scope. The candidate is not sent to the optional
`on_receipt_observed(OutputCommandReceipt)` callback unless the existing safe
enable owner reports accepted after its final readback. False results, raised
errors, and absence of a typed Native receipt expose nothing. Callback errors
are swallowed so observation cannot change physical transaction outcome. The
scope token is always reset in `finally`.

The existing coordinator and Runtime/Strict/Managed safety guard chain remain
the actuator and safety authorities. Their method signatures and bool behavior
are unchanged. `request_verified_on()` remains a bool contract and is not made
receipt-aware here. No second ON action, output method, cache, serialized state,
timer, lease, or safety gate was introduced.

## Fake evidence

The new test module verifies:

- exact receipt object identity observed from one `command_output_with_receipt`
  call while `command_output()` retains its dict return;
- `ExecutionPort.enable()` emits the candidate only for an accepted existing
  enable result, and preserves its normal result shape;
- false result and exception do not emit; each transaction is invoked once;
- HA-shaped input, OFF receipts, and non-APPLIED receipts are ignored;
- concurrent async requests keep distinct candidates, and a later scope begins
  empty.

Combined run of the new fixture with B1030 receipt boundary, execution-port
policy, managed runtime safety, and B1024 Native phase evidence: **69 tests
passed**. `py_compile` and `git diff --check` passed. No test simulates or claims
physical hardware acceptance.

## Limits and status

This cut exposes the receipt to an optional callback on `ExecutionPort.enable()`
only. `request_verified_on()` call sites continue to receive their established
boolean contract and cannot observe a receipt. This preserves those contracts
and does not create another guard method. Physical receipt/evidence validation,
P3 live acceptance, P8 release acceptance, and node104 deployment remain HOLD.

No OVP/OCP behavior or release/pin paths changed. No shared checkpoint,
master-plan, handoff-canon, or runbook edits were made per task scope.
