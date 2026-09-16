# RD6018 V3 execution shadow validation model — EPIC H.0

Status: shadow validation only. No physical command, HA/ESP write, lease
operation or execution ownership transfer is possible in this phase.

## 1. Validation boundary

```text
V2 execution action       V3 ActuatorIntent
          \                 /
           v               v
          ExecutionShadowValidator
                    |
                    v
      parity + safety + readiness result
```

The validator compares already-created data objects. It does not create an
execution request, select an adapter, dispatch a command, perform readback or
call a physical owner.

## 2. Intent parity

The comparison covers:

- `OUTPUT_ON`;
- `OUTPUT_OFF`;
- `SET_VOLTAGE`;
- `SET_CURRENT`;
- containment, which must map to `OUTPUT_OFF` with an explicit safety context.

Fields compared:

| V2 action | V3 intent |
|---|---|
| operation | `requested_operation` |
| target | `target` |
| owner | `owner` |
| safety context | `safety_context` |
| rollback | `rollback_policy` |
| verification | `verification_expectation` |

## 3. Safety parity and readiness

The V3 intent must contain non-empty telemetry, lease, containment,
verification and limits references. Rollback and verification are typed and
explicit. Execution readiness additionally requires:

- approved/non-empty owner;
- selected adapter label;
- transport availability evidence;
- required readback expectation.

Readiness is an observation. `execution_ready=True` never authorizes execution.

## 4. Failure scenarios

The validator models, without triggering, these cases:

- command timeout;
- readback mismatch;
- stale telemetry;
- expired lease;
- unavailable transport.

Missing rollback/verification for timeout or mismatch is `unsafe_difference`.
Insufficient context for stale telemetry, lease expiry or transport failure is
`unresolved`. No failure classification sends OFF, renews a lease or changes
the V2 owner.

## 5. Result categories

- `equal` — V2 and V3 semantics match;
- `expected_difference` — representation differs but no safety/ownership
  meaning is weakened;
- `unsafe_difference` — owner, safety, rollback, containment or verification
  semantics differ unsafely;
- `unresolved` — required transport/readiness/failure evidence is absent.

Any `unsafe_difference` or `unresolved` result blocks future ownership
transfer. Results carry `physical_execution_performed=False`.

## 6. Acceptance criteria

EPIC H.0 is accepted when:

1. all four operations and containment have parity coverage;
2. safety context, limits, rollback and verification are validated;
3. owner, adapter, transport and readback readiness are checked;
4. all five failure scenarios are classified without side effects;
5. no HA/ESP write, lease operation, ExecutionDispatcher call or physical call
   is reachable;
6. V2 execution, START, ACTIVE and physical ownership remain unchanged.

Overall readiness: `EXECUTION_SHADOW_VALIDATED`, `NOT_READY_FOR_TAKEOVER`.

## Explicit non-goals

This phase does not execute `ActuatorIntent`, prove live hardware readback,
change V2 execution, alter lease ownership, write HA/ESP, enable START/ACTIVE
or perform physical output.

