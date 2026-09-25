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

The adapter prepares the V2 input and normalizes the V2 transaction outcome.
The injected V2 transaction owner retains controller, safety and physical
execution authority.

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

## Runtime boundary

The adapter is connected only through `ProductionStartExecutionPort`; it does
not create a second controller or physical path.
