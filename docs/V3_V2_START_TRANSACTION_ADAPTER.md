# V3/V2 START transaction adapter

## Boundary

```text
ApprovedStartPlan
        |
        v
V2StartTransactionAdapter
        |
        v
V2StartTransactionInput
        |
        v
existing start_profile_transactional()
```

The adapter currently prepares a data-only V2 input and normalizes a captured
V2 outcome. It does not call the controller, HA, safety coordinator or physical
layer. ACTIVE execution is explicitly disabled.

## Normalized outcomes

Execution status:

- `STARTED`;
- `FAILED`;
- `DENIED`;
- `CONTAINED`.

Rollback state:

- `NOT_REQUIRED`;
- `OFF_CONFIRMED`;
- `OFF_UNCONFIRMED`;
- `SESSION_CLEARED`;
- `SESSION_CONTAINED`.

The normalization preserves the important V2 distinction between a failed start
with confirmed OFF/session cleanup and a failure that remains contained because
OFF could not be confirmed.

## Remaining blockers

1. Connect the adapter to the preserved V2 transactional owner only behind an
   approved production port.
2. Prove mapping against real V2 transaction outcomes.
3. Preserve controller/FSM/session ownership and rollback ordering.
4. Complete physical bench validation before enabling ACTIVE.

