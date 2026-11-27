# B1026 — ON receipt observation boundary

**Status: BLOCKED at production receipt exposure; no production patch made.**

The ESP Native transport already creates the required typed receipt for the exact correlated terminal APPLIED command. The value is then unwrapped in `ESPHomeTransport.command_output()`, discarded by `ESPDirectConnector.enable_output()` and normalized to boolean by `HassClient._switch_service()`. `ExecutionPort.request_verified_on()` returns the safety owner's bool. Read-only Native report access cannot reconstruct the command receipt.

The safety path that must be preserved is layered: `RuntimeSafetyGuard.turn_on()` checks prior-OFF containment, invokes the raw adapter once, validates post-ON telemetry/envelope, and contains failures with verified OFF. `StrictRuntimeSafetyGuard.turn_on()` adds positively acknowledged lease arm and cleanup. `ManagedRuntimeSafetyGuard.turn_on()` adds managed OFF recovery and external-temperature reauthorization. ExecutionPort adds app-scoped serialization, recovery quarantine, guarded-restore and ownership gates. No existing API retrieves the completed receipt non-invasively.

## Bounded implementation contract for a future source cut

Candidate application observation signature:

```python
async def request_verified_on_with_receipt(
    self,
) -> tuple[bool, OutputCommandReceipt | None]: ...
```

It must share one private serialized transaction with existing
`request_verified_on() -> bool`. The boolean API remains behaviorally identical;
the optional receipt must be the actual object returned by the same physical
ON invocation and may not be cached, reconstructed, or taken from another
request. The shared transaction must preserve Runtime, Strict and Managed guard
ordering, lease arm/disarm, post-ON safety readback and verified-OFF
containment, recovery and guarded-restore blocks, and HANDS_OFF/autonomous/release
default-deny behavior. A backend without a typed receipt returns `None` while
retaining the current bool semantics.

Before implementation, establish one common internal ON transaction across the
Runtime/Strict/Managed overrides. Adding a connector-only receipt method cannot
cross the safety owner. Adding a second guard path that calls that connector
method can bypass or duplicate existing checks. This common-seam prerequisite
is the current blocker.

## Required fake fixtures

1. Successful observation returns the exact transport receipt object and records exactly one raw ON invocation.
2. Existing bool callers still receive `True`/`False` for the same transaction outcomes.
3. Raw ON false, exception, invalid receipt, invalid post-ON telemetry, and envelope failure preserve current verified-OFF containment and never report verified success.
4. A receipt from one invocation is never exposed by a later call that has no receipt.
5. Guarded-restore and recovery quarantine block before ON; existing guarded-resume release requirements stay intact.
6. HANDS_OFF, autonomous and release barriers block before ON; strict lease-arm rejection blocks before ON.
7. Existing OVP/OCP observation-only policy remains unchanged; no OVP/OCP trip, admission condition, or automatic threshold write is added.
8. B1024’s Native callback assembler accepts only the real typed receipt and same-generation fresh Native records; fake receipts remain fixture data only.

Current existing regression cohort at source HEAD `170aa91a7e7d8bc578f5dfa32d7fea12f411f9fa` passed 78/78 in the offline project venv (see `B1026_REPORT.md`). This does not test new propagation because no propagation code was added.

P3 live/physical evidence and B1020 Gate 3 remain **HOLD**. P0–P9 remains
98/103, with three P3 and two P8 physical/release gates on HOLD. No native
hardware or production action occurred.
