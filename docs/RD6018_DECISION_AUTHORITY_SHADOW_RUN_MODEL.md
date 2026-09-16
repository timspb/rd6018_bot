# RD6018 Decision Authority Shadow Run — EPIC K

Status: shadow rehearsal only. Live decision ownership remains V2. This model
does not call an execution boundary, controller, HA, ESP, lease or physical
output path.

## 1. Decision flow

```text
V2 decision --------------------+
                                v
                         comparison result
                                ^
V3 canonical candidate ----------+
                                |
                                v
                   provenance + handoff preparation
                                |
                         no dispatch / no takeover
```

The runner receives already-produced V2 and V3 `DecisionSnapshot` values. It
records the V3 value as a canonical candidate only when the rehearsal is not
blocked. V2 remains the current decision authority for every run.

## 2. Hypothetical Stage 1 behavior

The rehearsal models the future flow:

1. V3 produces a canonical decision candidate.
2. The candidate receives trace-linked provenance.
3. An execution-compatible handoff description is prepared for V2.
4. The handoff is marked `dispatched=False`; no command is sent.

The execution owner in the handoff is V2. This is preparation, not an
authority transfer.

## 3. Operator visibility; Transition events

Each run exposes:

- current authority: always `V2`;
- candidate authority: `V3`;
- approval state: `NOT_APPROVED_SHADOW_ONLY`;
- rollback state: `NOT_REQUESTED` or `REQUESTED`;
- transition history with timestamp and reason;
- `live_decision_ownership_changed=False`.

## 4. Statuses; Failure scenarios

`READY` means the V2/V3 comparison is equal and a candidate handoff can be
prepared. `WARNING` means the difference is explicitly classified as expected.
`BLOCKED` means no candidate handoff is prepared.

The following are blocked: V3 unavailable, bad decision, stale telemetry,
configuration conflict, decision conflict and rollback request. A blocked run
does not fall back through a new owner change; V2 remains current.

## 5. Rollback rehearsal

A rollback request is recorded as a transition event, exposes
`rollback_state=REQUESTED`, and keeps V2 as current authority. The runner does
not execute a rollback command because execution is outside this shadow scope.
The event is sufficient for later Stage 1 audit integration.

## 6. Acceptance invariants

- no V2 decision-owner change;
- no V2 execution or physical-owner change;
- no approval is inferred from a healthy comparison;
- no execution handoff is dispatched;
- no HA/ESP/lease/transport side effects;
- `LIVE_DECISION_OWNERSHIP_UNCHANGED`.
