# RD6018 Safety, Lease & Transport Parity Validation — WORKSTREAM 7

Режим: pure model/shadow validation. V2, HA, ESPHome and lease ownership are
unchanged. Production transport, hardware commands and cutover were not
connected or executed.

## Result

**Status: BLOCKED for production parity.**

The V3 models and failure classifications are implemented and tested, but the
actual ESPHome/RD contract has not been exercised on the target node. Therefore
the result is not `SAFETY_TRANSPORT_PARITY_VALIDATED` and is not production
ready.

## 1. SafetyTriggerOwnershipMap

`v3_core.parity_validation.safety_trigger_ownership_map()` covers:

- watchdog timeout;
- telemetry loss;
- transport failure;
- lease expiry;
- manual stop;
- emergency stop;
- invalid state;
- readback mismatch.

The modeled chain is:

```text
Detection -> V3 Safety Domain -> Containment Intent
          -> V3 Execution Boundary -> verification
```

All records use one logical V3 decision owner and require trace/verification.
Every record is `NEEDS_PARITY`, not `VALIDATED`, because no physical boundary
was exercised.

## 2. LeaseParityReport

The current reference contract remains:

- owner: `ESPHome/edge dead-man`;
- renewal: existing V2 `EdgeSafetyLease` path;
- TTL: 900 s;
- renewal interval: 300 s;
- expiry: local dead-man containment.

Covered scenarios:

1. valid lease;
2. expiry;
3. renewal failure;
4. duplicate owner;
5. restart during lease.

Duplicate ownership is rejected. The model does not renew, arm, disarm or
manipulate the lease.

## 3. TransportParityModel

The model covers available, unavailable, timeout, rejected, delayed and
corrupted responses. A transport acceptance is never sufficient for verified
physical success; only matching fresh observation produces `verified=True`.

Flow:

```text
ExecutionRequest -> Transport result -> Physical observation -> Verification
```

No production transport or hardware implementation is imported.

## 4. Telemetry failure validation

Telemetry states are:

- `fresh` → allow;
- `stale` → contain;
- `unavailable` → contain;
- `conflicting` → contain.

This is a conservative V3 decision model. It does not override the current V2
safety runtime or ESPHome dead-man.

## 5. RestartRecoveryValidationModel

Covered:

- restart during charging;
- restart during containment;
- stale actuator state;
- missing telemetry;
- missing lease.

Every case requires no automatic unsafe resume, fresh actuator verification and
fresh safety/lease validation.

## 6. BenchValidationMatrix

The matrix is defined in `v3_core.parity_validation.bench_validation_matrix()`
for normal command/readback, transport timeout, wrong readback, stale telemetry,
lease loss, safety triggers and restart recovery. It contains setup, expected
behavior and pass criteria only. No case was executed against hardware.

## Remaining blockers

1. exact ESPHome firmware/lease contract parity;
2. target RD transport response and readback timing;
3. verified-OFF behavior under lease expiry and transport loss;
4. supervised bench evidence for restart/rollback;
5. production adapter authorization and rollback procedure.

## Restrictions confirmed

No V2 runtime, V2 execution, HA ownership, ESPHome ownership, lease ownership or
physical output changed. No production-ready status is claimed.
