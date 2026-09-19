# RD6018 V3 Physical Adapter Model — WORKSTREAM 6

Режим: isolated bench transport only. Production cutover, live ownership,
V2/HA/ESPHome/lease changes and physical commands are disabled.

## 1. Boundary

```text
ActuatorIntent
    |
    v
ExecutionDispatcher
    |
    v
V3PhysicalAdapter
    |
    v
BenchTransport (in-memory only)
    |
    v
TransportResult + readback
    |
    v
AdapterVerificationResult
```

`V3PhysicalAdapter` contains only operation translation, transport invocation,
readback verification and result shaping. It contains no charge logic, safety
decision, UI or configuration precedence logic.

## 2. Adapter contract

Supported operations:

- `OUTPUT_ON`;
- `OUTPUT_OFF`;
- `SET_VOLTAGE`;
- `SET_CURRENT`;
- `STOP`;
- `CONTAINMENT`.

The adapter accepts only owner `V3 Execution Boundary`. Any other owner is
rejected. `rollback()` and `containment()` create intents; they do not dispatch
commands automatically.

## 3. Bench transport

`v3_core.bench_transport.BenchTransport` is deterministic and in-memory. It
supports explicit scenarios:

- success;
- timeout;
- unavailable;
- rejected command;
- wrong readback;
- stale state.

It is not an HA, ESPHome, serial, GPIO or RD implementation.

## 4. Configuration

Adapter parameters are resolved through the standalone V3
`ConfigurationAuthority`:

- `execution.command_timeout_s`;
- `execution.readback_timeout_s`;
- `execution.readback_tolerance`.

No adapter constant or hidden timeout is used. The authority defaults are
explicit schema values with provenance; they do not make the adapter
production-ready.

## 5. Verification results

Every adapter result contains:

- requested action;
- transport result;
- observed state;
- verification status;
- failure reason;
- trace id;
- rollback-required flag.

Statuses are `VERIFIED`, `UNVERIFIED`, `FAILED`, `TIMEOUT` and `STALE`.
Transport acceptance is never treated as physical success without readback.

## 6. Safety contract integration

Safety integration is contract-only:

```text
SafetyDecision -> ContainmentRequest -> ActuatorIntent
               -> ExecutionDispatcher -> V3PhysicalAdapter
```

The bench adapter does not make the safety decision and does not execute a real
OFF/relay/hardware command. Trace and rollback intent are preserved.

## 7. Test matrix

Covered by `tests/test_workstream6_physical_adapter.py`:

1. normal actuator execution and readback;
2. failed/unavailable/rejected transport;
3. wrong readback;
4. stale state;
5. containment intent;
6. rollback intent;
7. duplicate owner rejection;
8. dispatcher-to-adapter path;
9. direct physical call/import rejection;
10. configuration validation.

## Status

`PHYSICAL_ADAPTER_READY` means **bench adapter contract ready**, not production
ready. Production physical execution remains blocked pending exact target
transport, ESPHome/lease parity, supervised bench authorization and separate
cutover approval.
