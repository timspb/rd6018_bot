# RD6018 staged ownership cutover model — EPIC I

Status: model only. Live authority is unchanged. V2 remains the current
decision, execution, lease and physical owner; V3 remains shadow/candidate.

## Stage 0 — current shadow

| Authority | Owner |
|---|---|
| decision | V2 |
| execution | V2 |
| physical output | V2 |
| lease | V2/edge contract |
| configuration | V3 canonical view, V2 effective runtime |
| telemetry | V3 staged authority, V2 consumers retained |

Entry: current state. Approval: none. Health: V2 production healthy and V3
shadow optional. Rollback: stop V3 shadow. Abort: any shadow side effect,
namespace conflict or evidence corruption.

## Stage 1 — decision cutover model

| Authority | Owner |
|---|---|
| decision | V3 |
| execution | V2 compatibility shell |
| physical output | V2 |
| lease | V2/edge |
| configuration | V3 |
| telemetry | V3 |

Entry criteria: long-run shadow PASS, V2/V3 healthy, no unexplained decision or
safety conflicts, rollback ready. Approval: explicit decision cutover approval.
Health: V2 remains healthy execution owner and V3 decision health is PASS.
Rollback: explicit return to Stage 0 after V2 health and session verification.
Abort: conflict threshold, missing provenance, V3 crash, V2 unhealthy or lost
rollback evidence.

## Stage 2 — execution staged model

| Authority | Owner |
|---|---|
| decision | V3 |
| execution boundary | V3 boundary |
| rollback fallback | V2 |
| physical output | V2 until separate physical gate |
| lease | V2/edge |
| configuration/telemetry | V3 |

Entry criteria: Stage 1 accepted, H.0 execution shadow PASS, intent/safety/
verification parity PASS, explicit execution approval and rollback fallback.
Health: exactly one physical owner (V2), exactly one lease owner (V2/edge),
and V3 boundary has no direct physical path. Rollback: reject V3 requests and
return decision/execution model to Stage 0 or Stage 1. Abort: unsafe/unknown
parity, readback gap, transport ambiguity, lease divergence or any duplicate
physical/control owner.

## Stage 3 — full ownership model

| Authority | Owner |
|---|---|
| decision | V3 |
| execution | V3 |
| physical output | V3 approved boundary |
| lease | V3-approved single lease owner |
| configuration | V3 Configuration Authority |
| telemetry | V3 Telemetry Authority |

Entry criteria: Stage 2 evidence, physical bench pass, verified rollback,
emergency disconnect, independent readback, explicit full cutover approval and
no unresolved safety/configuration conflicts. Health: one owner per authority,
one physical owner, one lease owner, one telemetry authority and one
configuration authority. Rollback: verified return to V2 with no implicit old
session resume. Abort: any physical/readback/lease ambiguity, V2/V3 health
loss, failed rollback or operator/bench gate loss.

Stage 3 is not enabled by EPIC I.

## Transition rules

1. Transitions are sequential: Stage 0 → 1 → 2 → 3.
2. No passing metric, restart, process state or missing V2 signal implies
   ownership transfer.
3. Exactly one physical execution owner exists at every stage.
4. Exactly one lease owner exists at every stage.
5. Configuration and telemetry authority are singular and provenance-backed.
6. Rollback is explicit, verified and non-implicit.
7. A model transition changes only this candidate model, never live runtime
   ownership.

## Acceptance and blockers

`StagedOwnershipCutoverModel` rejects skipped stages, missing approval/health
gates and invalid owner combinations. It reports missing gates and abort
conditions without invoking runtime, transport, lease or physical code.

Overall readiness: `CUTOVER_MODEL_DEFINED`, `LIVE_OWNERSHIP_UNCHANGED`.

## Explicit non-goals

This EPIC does not change V2 runtime, START, ACTIVE, HA/ESP control, lease
ownership, physical output or any live authority.

