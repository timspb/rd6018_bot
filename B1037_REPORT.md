# B1037 — same-client canonical OFF receipt and Native readback

Run: `rd6018-b1037-20261126-r73-same-client-off-proof`
Branch: `codex/rd6018-b1037-same-client-off-proof-20261126`
Base HEAD: `97384fb6b1589aaa02b08c9b87fe42a0aeb56e54`
Scope: source and fake tests only; no shared canon/runbook/checkpoint edits.

## Result

Extended B1034's request-local receipt observation to capture an APPLIED typed
OFF receipt from the existing `ESPHomeTransport.command_output_with_receipt(False)`
call. `ExecutionPort.request_emergency_off_receipt()` now accepts an optional
ancillary `on_native_off_observed(receipt, sample)` callback. It calls that
callback only after the existing Guard returned the exact same receipt object
captured from the command. The scope resets in `finally`; unsupported backends,
failed/false receipt paths, and missing provenance do not call the observer.

The existing post-command Native projector accepts either direction and
requires one `SensorInfo`/`SensorState` for R18, measured voltage and current;
callback timestamps strictly after receipt completion and no older than 8 s;
the exact original transport and APIClient; unchanged connection generation;
one device ID; finite numeric V/I; and receipt-matching typed integer R18.
For OFF, measured voltage and current must be exactly zero. Invalid, stale,
preterminal, missing, wrong-type or changed-origin data returns
`NOT_OBSERVED`. No second OFF command, retry, timer, delay, or HA fallback was
introduced. The typed OFF receipt return and Guard validation remain unchanged.

## Changed paths

- `application/execution_port.py` — optional ancillary callback around the
  existing emergency OFF receipt call.
- `runtime/output/command_receipt_observation.py` — request-local APPLIED OFF
  receipt capture, reusing B1034's context and reset mechanism.
- `runtime/physical/transports/esp128.py` — direction-aware projection using
  B1036's existing callback records and strict same-source checks.
- `tests/test_b1037_same_client_native_off_readback.py` — focused OFF fakes,
  including the complete composed route.
- `B1037_REPORT.md`, `docs/acceptance/B1037_SAME_CLIENT_NATIVE_OFF_READBACK.md`.

## Verification

HOME-PC project venv `/home/home-pc/.venvs/pcp-test/bin/python`,
`PYTHONPATH=.:tests:tools`, inert test-only `TG_TOKEN`:

```text
tests.test_b1037_same_client_native_off_readback
tests.test_b1034_tasklocal_on_receipt
tests.test_execution_port_policy_boundary
tests.test_node104_d091_physical_proof_collector
tests.test_typed_off_receipt_ad095
57 tests — PASS
```

The fake coverage includes one existing OFF command and exact returned receipt
identity; post-terminal zero R18/U/I from the same composed ESP transport and
client; stale, preterminal, missed, nonzero, malformed, wrong-type, changed
client/transport/generation rejection; ancillary `NOT_OBSERVED`; request scope
reset; and unsupported/failed OFF receipt behavior. `py_compile` and
`git diff --check` passed.

This is source/fake acceptance only. No physical Native data was collected and
no physical P3 PASS is claimed. P0–P9 remains 98/103; the three P3 physical and
two P8 physical/release items remain HOLD. Existing D106 OFF and D151 pinned
collector are untouched. No R16, OVP/OCP, guard, lease, setpoint, firmware,
deployment or actuator policy was changed. No node104/ESP/HA/RD hardware,
Output, service, SSH, network/GitHub, commit, push, staging, or original dirty
checkout action occurred. Draft PR #182 and main remain unchanged.
