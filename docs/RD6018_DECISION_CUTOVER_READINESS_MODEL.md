# RD6018 Stage 1 decision cutover readiness — EPIC J

Status: preparation only. This model does not change live ownership. V2
remains the production decision, execution and physical owner.

## 1. Stage 1 authority flow

```text
V3 shadow decision
        |
        v
canonical decision + provenance
        |
        v
execution-compatible request (candidate only)
        |
        v
V2 execution owner
        |
        v
V2 physical owner
```

Stage 1 prepares V3 as a decision-owner candidate while V2 remains the only
execution and physical owner. The readiness model does not dispatch the
candidate request.

## 2. Approval mechanism

Approval requires an immutable `Stage1ApprovalRecord` containing:

- explicit enable;
- approval ID;
- timestamp;
- operator;
- source;
- rollback authority.

Approval is rejected unless all Stage 1 gates pass. A process restart, healthy
shadow runtime, passing comparison or missing V2 signal cannot create implicit
approval.

## 3. Safety gates

All are required:

- long-running shadow acceptance `PASS`;
- no unresolved safety conflicts;
- healthy telemetry authority;
- stable configuration/provenance;
- healthy V2/V3 runtime.

Missing gates leave the candidate `NOT_READY` and cannot be approved.

## 4. Rollback

Rollback returns the decision candidate to V2 immediately at the model level.
It records an audit event with source, timestamp, previous/current owner and
reason. Rollback never calls execution, stops hardware, writes HA/ESP, renews
a lease or resumes an old session.

Rollback triggers include:

- any unresolved safety conflict;
- telemetry/configuration/runtime health loss;
- decision parity blocker;
- failed operator or physical gate;
- failed or ambiguous rollback verification.

## 5. Observability

`DecisionCutoverReadiness` exposes:

- readiness state;
- current candidate decision owner;
- execution owner;
- physical owner;
- gate status and missing gates;
- approval record;
- transition history;
- `live_ownership_changed=False`.

Expected Stage 1 candidate state:

```text
decision owner: V3-candidate
execution owner: V2
physical owner: V2
live ownership changed: false
```

## 6. Acceptance criteria

EPIC J preparation is ready when:

1. all gates are represented and evaluated;
2. approval is explicit, attributable and timestamped;
3. V3 decision provenance is retained;
4. rollback to V2 is tested and auditable;
5. execution/physical ownership remains V2;
6. no HA/ESP/lease/physical side effect is reachable.

Overall readiness: `STAGE1_READINESS_MODEL_READY`, `LIVE_OWNERSHIP_UNCHANGED`.

## Explicit non-goals

This EPIC does not enable Stage 1, change V2 runtime, change START/ACTIVE,
write HA/ESP, alter lease ownership or perform physical output.

