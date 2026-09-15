# RD6018 Decision Canary — EPIC M

Status: model-only decision authority control. Execution ownership remains V2
and no canary method calls a controller, transport, HA, ESP, lease or physical
output path.

## States

```text
DISABLED -> SHADOW -> CANARY -> ACTIVE_DECISION
                         |              |
                         +--------------+
                                |
                             ROLLBACK
```

- `DISABLED`: no decision canary is enabled.
- `SHADOW`: V3 may be observed without authority.
- `CANARY`: bounded V3 decision authority is modeled for the declared scope.
- `ACTIVE_DECISION`: V3 decision authority remains bounded by the canary.
- `ROLLBACK`: V2 decision authority is restored in the model.

The transitions are not runtime wiring. They prepare the Stage 1 contract.

## Canary parameters

Every canary has:

- `scope` — explicit battery/session or other bounded target;
- `duration` — positive finite interval;
- explicit approval with operator, source and rollback authority;
- `expiry` — automatic rollback deadline;
- `rollback_policy` — default is automatic rollback on blocker or expiry.

## Authority boundary

During `CANARY` or `ACTIVE_DECISION`:

- V3 may generate the decision and provenance and expose authority state;
- V2 remains execution owner;
- V2 remains physical-output owner;
- lease ownership is unchanged;
- no command is dispatched.

## Automatic blockers

The controller rolls back when it observes:

- safety conflict;
- unhealthy telemetry;
- configuration conflict;
- runtime failure;
- unexplained divergence;
- canary expiry.

Blockers are retained in the health snapshot and audit history.

## Audit and health visibility

Each transition records timestamp, source, reason, scope and previous/next
state. Snapshots expose current decision owner, execution owner, physical owner,
approval, expiry, rollback policy, health blockers and transition history.

## Invariants

- one decision canary scope at a time in this model;
- no implicit approval;
- expiry and blocker paths return decision authority to V2;
- execution ownership never changes;
- physical ownership never changes;
- `LIVE_EXECUTION_OWNERSHIP_UNCHANGED`.

