# RD6018 Actuator Execution Parity

Status: Phase 4.3 analysis only. No execution wiring is added.

## Compared paths

```text
Current:
V2 transaction -> controller/FSM -> SafeOutputCoordinator -> physical boundary

Future dry-run contract:
ActuatorIntent -> ActuatorIntentAdapter -> V2ActuatorExecutionRequest
                                      -> existing owner (not called here)
```

## Field parity

| Operation | Current V2 request | Adapter request | Result |
|---|---|---|---|
| `OUTPUT_ON` | source, owner, target, reason, safety preconditions, transaction rollback | source, owner, target, reason, safety context | data parity for carried fields; rollback is not a first-class field |
| `OUTPUT_OFF` | source, owner, target, reason, OFF/readback/containment semantics | source, owner, target, reason, safety context | data parity for carried fields; verification/rollback remains implicit |
| `SET_VOLTAGE` | source, owner, target voltage, envelope/readback/precondition safety | source, owner, target voltage, safety context | target and safety context carried; precondition semantics are not typed |
| `SET_CURRENT` | source, owner, target current, envelope/readback/precondition safety | source, owner, target current, safety context | target and safety context carried; precondition semantics are not typed |

## Findings

### Preserved semantics

- operation is explicit and restricted to four known values;
- source, owner, target, reason and safety context are carried unchanged;
- invalid owner/source and explicitly blocked safety context are rejected;
- adapter does not call the existing owner or any physical layer.

### Semantic drift or missing contract fields

1. `rollback_expectation` is not a first-class field in `ActuatorIntent` or
   `V2ActuatorExecutionRequest`. It remains implicit in `reason`/context and
   existing owner behavior.
2. `trigger` is not carried into the adapter request; trace correlation alone
   is insufficient for complete post-incident reconstruction.
3. `safety_context` is a free-form mapping. Required checks such as ownership,
   freshness, readback and lease state are not schema-typed.
4. The adapter's V2 request makes no claim about physical verification. A
   constructed request is not evidence that the operation succeeded.
5. Owner strings are exact textual values; renaming an owner can create drift
   without a typed identity contract.

### Ownership ambiguity

- `OUTPUT_ON` has multiple valid current owners (V2 transaction, Manual and
  V2 runtime safety surface). The adapter validates the declared owner but does
  not establish which composition root is authoritative.
- `OUTPUT_OFF` has several containment owners. The request does not distinguish
  normal stop, emergency stop, watchdog containment and lease preservation.
- diagnostic setpoint operations are classified separately, but their future
  execution authority must remain explicitly gated.

### Unsafe defaults

- a caller can construct a syntactically valid request without typed rollback
  or verification requirements;
- arbitrary target types are accepted by the data-only request;
- a mapping that says `safety_context={"checked": True}` is structurally valid,
  but does not prove any actual safety evidence.

These are analysis findings only. They are not fixed in Phase 4.3 because doing
so would change the adapter contract and requires a separate reviewed phase.

## Parity decision

Current adapter is suitable for dry-run observation and field-preserving
translation only. It is not yet sufficient as an execution authorization
contract until rollback expectation, trigger identity, typed safety evidence
and physical verification/result mapping are explicitly represented.

