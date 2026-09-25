# RD6018 Decision Cutover Operational Readiness — EPIC L

Status: preparation only. Live ownership is unchanged. V2 remains the current
decision, execution and physical owner; V3 is an operational candidate only.

## 1. Operator visibility

The operational snapshot exposes:

- current decision owner: `V2`;
- candidate owner: `V3`;
- execution owner: `V2`;
- physical owner: `V2`;
- transition state;
- health gates and missing gates;
- approval lifecycle state;
- audit trail;
- `live_ownership_changed=False`.

## 2. Approval lifecycle

Approval is explicit and attributable. The immutable approval record contains:
approval ID, operator, timestamp, source, rollback authority, explicit enable
and expiry. Approval is allowed only after all five Stage 1 health gates pass.

The model supports:

```text
NOT_APPROVED -> APPROVED -> EXPIRED
                         -> REVOKED
                         -> EMERGENCY_ROLLBACK_TO_V2
```

Expiry and revoke return the decision authority to the V2 operational model.
Healthy shadow output, process restart or missing operator input cannot create
implicit approval.

## 3. Emergency controls

The model-only controls are:

- `emergency_rollback`: immediate return of decision authority to V2;
- `disable_v3_decision`: explicit emergency alias for the same action;
- revoke approval before cutover.

These controls update the audit/readiness model only. They do not stop a
controller, send Output OFF, write HA/ESP, change a lease or invoke physical
execution.

## 4. Audit trail

Each health evaluation, approval, expiry, revoke and emergency rollback records:

- event type and timestamp;
- source/operator context;
- current and candidate decision owner;
- execution and physical owner;
- transition state;
- reason.

## 5. Health gates

All are required before approval:

- runtime healthy;
- telemetry healthy;
- configuration stable;
- long-running shadow acceptance `PASS`;
- no unresolved safety conflicts.

Missing gates produce `NOT_READY` and block approval.

## 6. Ownership invariants

This EPIC does not enable Stage 1. At every snapshot:

- V2 remains current decision owner;
- V3 is only the candidate owner;
- V2 remains execution owner;
- V2 remains physical owner;
- HA, ESP, lease and physical paths are unreachable;
- `LIVE_OWNERSHIP_UNCHANGED`.

