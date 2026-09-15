# RD6018 V3 decision ownership migration model — EPIC G

Status: decision-authority preparation only. Execution is forbidden. V2
remains both the production decision owner and execution owner until an
explicit future migration gate is approved.

## 1. Current and target ownership

| Concern | Current | Target | EPIC G mode |
|---|---|---|---|
| FSM decision | V2 active | V3 domain | shadow |
| phase transition | V2 active | V3 domain | shadow |
| strategy decision | V2 active | V3 Strategy Domain | shadow/advisory |
| termination decision | V2 active | V3 Strategy Domain | shadow/advisory |
| safety recommendation | V2 safety owners | V3 Safety Domain recommendation | shadow |
| containment recommendation | V2 containment owners | V3 candidate recommendation | shadow |
| physical execution | V2 | unchanged V2 until separate execution migration | never changed by EPIC G |

The V3 decision owner target is deliberately independent from physical
execution. A V3 decision or recommendation is not an actuator command and
cannot bypass the V2 execution boundary.

## 2. Authority modes

| Mode | Decision owner | V3 output | Execution |
|---|---|---|---|
| shadow | V2 | compared candidate | V2 only |
| advisory | V2 | recommendation/evidence | V2 only |
| staged | explicitly approved V3 | selected V3 decision for approved scope | V2 compatibility shell only |
| active decision | explicitly approved V3 | V3 decision | still separate; no physical execution in EPIC G |

`DecisionAuthorityCoordinator` starts in `shadow` with V2 authority. Staged or
active-decision mode requires explicit approval. A passing comparison, V3
health, process restart or missing V2 signal cannot implicitly promote V3.

## 3. DecisionAuthorityCoordinator

The coordinator:

- stores current mode and decision owner;
- compares the same-input V2/V3 `DecisionSnapshot` values;
- records trace, source, authority, mode, comparison status and reason;
- selects V2 in shadow/advisory mode;
- selects V3 only after explicit staged/active approval;
- refuses implicit V2 fallback when explicitly selected V3 output is missing;
- provides an explicit rollback to V2 shadow authority.

It does not import or call `ExecutionDispatcher`, controller, SafetySupervisor,
SafeOutputCoordinator, HA, ESPHome, lease or physical adapters.

## 4. Ownership parity surface

Comparison covers:

- FSM state and phase;
- profile and strategy decision;
- target values;
- safety limits and warnings;
- termination result;
- containment recommendation;
- generated actuator intent as data only.

Results use the existing comparison statuses `equal`, `expected_difference`,
`conflict` and `unknown`. Every result has decision provenance. Divergences
remain evidence until explained and approved.

## 5. Rollback and failure rules

| Condition | Action | Result |
|---|---|---|
| V3 decision missing in V2-owned mode | retain V2 | no takeover |
| V3 decision missing in V3-approved mode | select nothing and record reason | no implicit V2 takeover |
| unexpected/conflicting parity | remain V2-owned | migration blocker |
| V3 runtime crash | rollback/stop shadow consumer | V2 decision/execution remain |
| V2 rollback request | `rollback_to_v2()` | shadow mode, V2 owner |
| physical/transport signal | outside coordinator | no execution call |

Rollback changes logical decision authority only. It does not start/stop
hardware, write HA/ESP, renew a lease or restore an old session.

## 6. Acceptance criteria

EPIC G preparation is complete when:

1. all decision surfaces have explicit current/target owners;
2. authority mode transitions require explicit approval for V3 authority;
3. V2/V3 comparison and provenance are trace-correlated;
4. rollback to V2 is explicit and tested;
5. no coordinator path calls execution or physical layers;
6. `V3 decision != physical execution` remains enforced;
7. V2 execution, HA/ESP, lease, START and ACTIVE remain unchanged.

Overall readiness: `DECISION_SHADOW_READY`, `NOT_READY_FOR_DECISION_CUTOVER`.

## Explicit non-goals

This EPIC does not change V2 execution, start/stop behavior, safety ownership,
HA/ESP control, lease ownership, START/ACTIVE, ExecutionDispatcher or physical
output.

