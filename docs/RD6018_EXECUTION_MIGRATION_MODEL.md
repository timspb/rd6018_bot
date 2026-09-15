# RD6018 V3 execution migration model — EPIC D

Status: contract/shadow preparation. V2 remains the production execution and
physical owner. No adapter is connected and no physical execution is
authorized by this model.

## 1. Execution ownership

| Layer | Current owner | Target owner | EPIC D mode | Rollback |
|---|---|---|---|---|
| intent creation | V2/domain shadow inputs | V3 Application/Domain | observe | discard V3 intents |
| validation/routing | V2 boundary plus V3 `ExecutionDispatcher` contract | V3 Execution Boundary | dry-run | retain V2 route |
| adapter selection | V2/transport owner | V3 composition | staged | restore V2 adapter selection |
| physical command | V2 transaction/SafeOutput owner | V3 boundary through approved owner | not connected | V2 remains authoritative |
| readback/verification | V2 transaction and safety owners | V3 evidence boundary | shadow comparison | retain V2 verification |

Listing V3 as a target does not transfer ownership. A future transfer requires
an explicit cutover decision, physical-gate approval, verified rollback and
separate bench evidence.

## 2. Execution pipeline

```text
ActuatorIntent
      |
      v
Validation
      |
      v
ExecutionRequest
      |
      v
Adapter
      |
      v
Physical command       [NOT CONNECTED IN EPIC D]
      |
      v
Readback               [SHADOW EVIDENCE ONLY]
      |
      v
Verification           [CONTRACT RESULT, NOT HARDWARE PROOF]
```

The V3 boundary may validate an intent and return a deferred result. It must
not call an adapter, controller, SafeOutputCoordinator, HA/ESP client or
physical method in EPIC D.

## 3. Safety gates before any future execution

Every future execution request must carry all of the following before adapter
selection:

1. valid `ActuatorIntent` and supported operation;
2. approved execution owner;
3. typed `SafetyContext`;
4. explicit `RollbackPolicy`;
5. typed `PhysicalVerificationExpectation`;
6. trace/correlation identity;
7. current configuration provenance and applicable limits.

Missing or invalid context is a rejection, not a default. A deferred
`ExecutionResult` is not evidence that a command was sent or verified.

## 4. Migration modes

| Mode | Meaning | Physical action | Exit criterion | Rollback |
|---|---|---:|---|---|
| observe | record existing V2 requests and outcomes | no | complete reachability map | stop observer |
| dry-run | validate V3 intent and build request | no | parity and rejection tests pass | reject V3 request |
| dual-run | calculate V2 and V3 requests side by side | no V3 action | sustained parity evidence | V2 remains sole executor |
| staged | limited approved boundary with explicit gate | not implied | bench/ownership approval | return to V2 owner |
| cutover | separately authorized ownership transfer | only after approval | production gate and verification | verified V2 rollback |
| rollback | remove V3 execution authority | V2 only | V2 owner healthy and evidence retained | no silent resume |

EPIC D is limited to observe and dry-run. Dual-run is a future evidence mode;
staged/cutover are not enabled by this commit.

## 5. Execution parity

The comparison unit is an existing V2 action versus a V3 `ActuatorIntent`.
The comparison does not execute either side.

| V2 action field | V3 intent field | Required comparison |
|---|---|---|
| operation | `requested_operation` | exact operation equality |
| target/setpoint | `target` | value and unit equivalence |
| owner | `owner` | approved ownership equivalence |
| trigger/reason | `trigger` / `reason` | causal traceability |
| safety context | `safety_context` | all required fields present and equivalent |
| rollback | `rollback_policy` | explicit policy equivalence |
| readback/verification | `verification_expectation` | expected state and timeout reference |

Results are classified as:

- **equal** — semantic fields match;
- **expected difference** — an approved boundary representation difference;
- **unsafe difference** — missing/weaker owner, rollback, safety or
  verification semantics; blocks migration;
- **unknown** — insufficient evidence; blocks migration until explained.

Every non-equal result requires trace/correlation and a divergence explanation.
No unsafe difference may be normalized by choosing a permissive default.

## 6. Execution readiness model

| Readiness area | Ready condition | Current EPIC D state |
|---|---|---|
| contract | intent/request/result schemas are immutable and typed | PASS |
| ownership | owner is explicit and allow-listed; no UI/direct physical owner | PASS for shadow |
| safety | context, rollback and verification are mandatory | PASS for shadow |
| parity | equal/expected/unsafe/unknown classification is available | PASS for model; evidence pending |
| adapter | adapter contract exists but is not connected | PASS for shadow |
| readback | observation shape exists; hardware proof remains V2-owned | SHADOW ONLY |
| rollback | V2 request rejection/retention path is defined | REQUIRED before staged mode |
| physical gate | explicit operator/bench/rollback/readback approvals | NOT SATISFIED |

Overall readiness: `NOT_READY_FOR_EXECUTION`.

## 7. Acceptance and rollback

EPIC D shadow acceptance requires:

1. intent validation and owner checks pass;
2. missing rollback or verification context is rejected;
3. all operation mappings remain transport-free;
4. no physical calls, HA writes or ESP writes are reachable from the shadow
   path;
5. V2 execution, START, ACTIVE and physical tests remain unchanged and pass;
6. any unsafe or unknown parity result remains a blocker;
7. rollback returns to the unchanged V2 execution owner.

Rollback is non-physical: stop accepting V3 candidate requests and retain all
V2 execution/verification/containment behavior. No old session is resumed
implicitly.

## Explicit non-goals

This EPIC does not execute `ActuatorIntent`, call `ExecutionDispatcher` with a
physical adapter, change V2 execution, write HA/ESP, change START/ACTIVE,
modify SafeOutputCoordinator, or alter physical output ownership.

