# B1034 — request-scoped typed ON receipt observation

Run: `rd6018-b1034-20261126-r73-tasklocal-receipt`
Branch: `codex/rd6018-b1034-tasklocal-receipt-20261126`
Base HEAD: `2d4fbd1d1235251215c5dceeeba07ef3fd69879e`
Draft PR: #182 (not accessed or changed)

## Result

Implemented an optional, request-scoped observation path for the existing
`ExecutionPort.enable()` transaction. When the configured direct ESP Native
transport returns its already-created immutable `OutputCommandReceipt`,
`ESPHomeTransport.command_output()` offers that exact object to the current
async request context and still returns the same decoded terminal dictionary.
The optional `ExecutionPort.enable(on_receipt_observed=...)` callback receives
that exact receipt only after the existing safe-enable owner returns accepted,
which includes its existing final readback acceptance. Legacy `enable()` result
shape and `request_verified_on() -> bool` are unchanged.

Observation uses a `ContextVar` with a fresh candidate slot for each `enable`
call. Its token is reset in `finally`; no receipt is stored on a long-lived
owner or reused by later tasks. The observer only accepts typed ON/APPLIED/R18=1
receipts. HA102 supplies no Native receipt. No guard, coordinator, lease,
containment, recovery, or output dispatch path was added or bypassed. The
existing raw ON is still issued once.

The safety-backed receipt is exposed on the accepted `ExecutionPort.enable()`
path. The legacy `request_verified_on()` boolean path remains unchanged and
does not expose a receipt in this bounded change.

## Changed paths

- `runtime/output/command_receipt_observation.py` — task-local candidate slot.
- `runtime/physical/transports/esp128.py` — notify from the one existing
  receipt-bearing command call while preserving the decoded dict return.
- `application/execution_port.py` — optional acceptance callback after
  `SafeOutputCoordinator`/owner final result; scope reset in `finally`.
- `tests/test_b1034_tasklocal_on_receipt.py` — fake-only behavior coverage.
- `B1034_REPORT.md`
- `docs/acceptance/B1034_TASKLOCAL_ON_RECEIPT.md`

## Verification

Using `/home/home-pc/.venvs/pcp-test/bin/python`,
`PYTHONPATH=.:tests:tools`, and inert `TG_TOKEN`:

```text
tests.test_b1034_tasklocal_on_receipt
tests.test_b1030_on_receipt_boundary
tests.test_execution_port_policy_boundary
tests.test_managed_runtime_safety
tests.test_b1024_native_phase_evidence
Ran 69 tests — OK
```

The fake tests cover receipt object identity from a single command call,
decoded-dict and boolean compatibility, exposure only after accepted result,
no exposure on false/exception, HA/non-Native and non-APPLIED exclusion,
concurrent context isolation, and reset between requests. The existing execution
policy cohort covers HANDS_OFF/release/adopted authority barriers; managed
safety tests cover existing lease, failure containment, OPP and diagnostic
R16=1/2 behavior. These are software fakes/source checks, not physical evidence.

`py_compile` — PASS for all three changed Python production modules and the new
test. `git diff --check` — PASS.

No OVP/OCP automatic writes, checks, or threshold programming were introduced;
the release/pin paths were not changed. No live ESP/HA/RD, node104, firmware,
Output, setpoints, service, deployment, network, SSH, GitHub, staging, commit,
push, original dirty tree, or additional Codex execution was used. Shared
checkpoint/master/handoff/runbook documents were not modified. Wake R7.3 owns
completion; no hook was called manually.

P0–P9 remains 98/103; three P3 and two P8 physical/release items remain HOLD.
No release or physical acceptance is claimed.
