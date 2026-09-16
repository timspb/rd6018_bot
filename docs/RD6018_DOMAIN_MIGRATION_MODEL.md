# RD6018 V3 domain migration model — EPIC B

Status: domain migration checkpoint. This document normalizes the V1/V2
charging semantics into the existing pure V3 domain contracts. It does not
wire the domain to production, replace V2 ownership, or authorize execution.

## Scope and authority

The migration path is deliberately one-way for evidence, not for control:

```text
V2 behavior
    |
    v
V3 pure-domain behavior
    |
    v
V2/V3 comparison
    |
    v
Divergence explanation
```

V2 remains the active owner of production FSM/session/safety/execution. V3
owns only the pure shadow representation and its comparison evidence. All
profile and strategy parameters are inputs from `ConfigurationAuthority`; no
profile may introduce hidden constants or transport access.

Classification used below:

- **EXPECTED** — an intentional boundary or already accepted representation;
- **UNRESOLVED** — a decision is still open and must not be guessed;
- **BUG** — an implementation defect to fix before acceptance;
- **ARCHITECTURAL IMPROVEMENT** — a safer separation that preserves behavior.

## 1. Charge FSM domain

### Ownership and model

`ChargeEngine` owns the pure transition table and phase lifecycle. It consumes
validated domain input and emits a domain decision. It does not call a
controller, mutate V2 state, or perform an actuator operation.

| Concern | V2 behavior | V3 behavior | Classification |
|---|---|---|---|
| lifecycle | IDLE/PREP/MAIN/recovery/MIX/SAFE_WAIT/COOLING/DONE with production owner | same canonical phase vocabulary with strict transition validation | EXPECTED |
| guards | profile, evidence, limits and safety gates guard transitions | guards remain domain inputs; infrastructure failures are not hidden in FSM | ARCHITECTURAL IMPROVEMENT |
| invalid transition | rejected by the active owner | rejected without unrelated state mutation | EXPECTED |
| completion | accepted evidence/hold reaches DONE; timeout is not success | decision reports completion/reason; outer owner remains responsible for containment/OFF | EXPECTED |
| restart | requires fresh validation and operator authorization | candidate restore only; never physical resume | ARCHITECTURAL IMPROVEMENT |

Parity gate: every accepted V2 transition must have a V3 transition vector;
every rejected V2 transition must remain rejected or be explicitly classified
as unresolved. No transition is promoted from a shadow result alone.

## 2. Profile domain

`ProfileRegistry` owns immutable domain definitions and explicit Custom
registration. The registry is not a second configuration source: values come
from the validated `ConfigurationAuthority` snapshot and carry provenance.

| Profile | V2 baseline | V3 domain representation | Classification |
|---|---|---|---|
| AGM | staged Main/CV behavior, 2 h tail/hold semantics, Mix authority 10 h | factory recipe with Main 15.0 V/8 A, 0.2 A tail, 2 h hold and Mix authority 10 h | EXPECTED |
| EFB | Main about 14.8 V, Mix ceiling 16.5 V; historical 20 h and V2 24 h sources | validated recipe currently represents 24 h and preserves the conflict as evidence | UNRESOLVED |
| Ca/Ca | Main about 14.7 V, Mix 16.5 V, Delta/hold termination, 20 h authority | validated factory recipe with 20 h Mix authority | EXPECTED |
| Custom | explicit Main/Mix values, Delta, hold and time limit bounded by envelope | explicit registration only; no chemistry fallback | ARCHITECTURAL IMPROVEMENT |

Profile acceptance requires identity, chemistry, phase targets, termination
strategy, hold/timer and validated limits. Missing fields are a rejected
profile, not an inferred default.

## 3. Strategy domain

`StrategyEngine` and the pure strategy contracts own CC/CV evaluation,
termination evidence, confirmations, Delta tracking, timers and holds.

| Strategy area | V2 behavior | V3 behavior | Classification |
|---|---|---|---|
| CC | Vmax is followed by confirmed Delta-V evidence | current pure implementation has a current-drop/Delta program representation | UNRESOLVED |
| CV | Imin is captured, confirmed Delta-I is required, then sticky hold | `CVMixExitPolicy` models Imin, confirmations and hold | EXPECTED |
| absorption | bounded phase with evidence and hold before completion | explicit phase/strategy decision without physical command | EXPECTED |
| float | profile/strategy-defined continuation or terminal behavior | represented as a domain phase/decision only where configured | UNRESOLVED if profile does not define it |
| hold | confirmed evidence starts a sticky hold; timeout is not successful completion | configurable `hold_seconds`, with the current 2 h contract retained | EXPECTED |
| timer | chemistry authority limits active Mix | EFB 20 h/24 h remains unresolved; Ca/Ca 20 h and AGM 10 h are represented | UNRESOLVED |

The CC Vmax/Delta-V versus current-drop difference is not silently corrected.
It requires golden vectors and an explicit domain decision before any future
cutover.

The Custom profile schema remains an explicit unresolved design decision; the
current contract rejects incomplete Custom definitions rather than inventing
fields or defaults.

## 4. Session domain

`SessionManager` owns only logical start/stop/pause/resume state. V2 remains
the production session and physical owner.

| Concern | V2 behavior | V3 behavior | Classification |
|---|---|---|---|
| start | creates a managed session after identity/profile/preflight | creates logical ACTIVE session after required identifiers are present | EXPECTED |
| stop | terminates session and production owner performs physical containment | reaches logical STOPPED; emits no physical action | EXPECTED boundary |
| pause | operator-controlled pause of active session | ACTIVE → PAUSED only | EXPECTED |
| resume | requires valid paused session and current safety checks | PAUSED → ACTIVE logically; physical resume remains outside domain | ARCHITECTURAL IMPROVEMENT |
| restart | recovery is not an implicit physical resume | candidate restore requires fresh telemetry, preflight and operator authorization | ARCHITECTURAL IMPROVEMENT |

## 5. Safety domain

V3 safety domain logic consumes configuration, validated telemetry and domain
context. It produces limits/envelope findings and containment
recommendations. Existing V2 SafetySupervisor, SafeOutputCoordinator, lease
and physical containment remain authoritative.

| Safety area | V2 behavior | V3 behavior | Classification |
|---|---|---|---|
| limits/envelopes | chemistry and physical bounds are enforced by V2 owners | pure limits/envelope evaluation returns evidence/recommendation | ARCHITECTURAL IMPROVEMENT |
| stale telemetry | infrastructure/runtime safety may contain according to current policy | stale/freshness is an explicit input and recommendation, not a hidden transport call | ARCHITECTURAL IMPROVEMENT |
| temperature/current/voltage | V2 safety owners can reject/contain | V3 domain records the decision and reason without writing outputs | EXPECTED boundary |
| containment | existing owner performs verified OFF/lease behavior | V3 emits `ContainmentResultRequest` candidate only | EXPECTED boundary |

No V3 safety result changes V2 safety behavior during EPIC B.

## 6. Comparison and divergence explanation

Each migration block must produce comparable inputs and a trace-correlated
result. Comparison must distinguish equal, expected difference, unresolved,
bug and architectural improvement. `DivergenceExplanationEngine` supplies
category, source, V2 value, V3 value, expectedness and confidence.

Required comparison coverage:

| Block | Comparison inputs | Minimum evidence |
|---|---|---|
| FSM | state, transition, guard, completion reason | accepted/rejected transition vectors |
| profiles | profile identity, phase targets, timers, limits | AGM/EFB/Ca/Ca/Custom fixtures and provenance |
| strategy | phase, measurements, evidence, hold/timer state | CC, CV, Delta and timeout golden scenarios |
| session | intent, lifecycle state, restart context | start/stop/pause/resume/restart candidate scenarios |
| safety | measurements, freshness, limits, lease/containment context | limit, stale, readback and containment recommendations |

An unexplained divergence is a blocker for EPIC B acceptance. An unresolved
divergence is recorded as a blocker, not converted to an automatic V3 rule.

## 7. EPIC B acceptance and rollback

EPIC B is ready only when:

1. all five domain blocks have parity tests and trace-correlated comparison;
2. profile/strategy parameters have ConfigurationAuthority provenance;
3. every difference is classified and every unresolved decision is listed;
4. no unexplained safety or containment divergence remains;
5. tests prove the domain has no Telegram, HA, ESPHome, transport,
   persistence or physical imports;
6. V2 production tests remain unchanged and pass.

Rollback is non-operational: stop consuming V3 candidate decisions and retain
V2 as decision/session/safety/execution owner. No V3 state is restored into a
physical or active V2 session.

## 8. Explicit non-goals

This EPIC does not:

- change START or ACTIVE;
- replace V2 FSM, controller, session or safety ownership;
- connect Telegram, HA, ESPHome or RD transport;
- call `ExecutionDispatcher` with production effects;
- write HA/ESP/RD or perform physical execution;
- resolve EFB, CC, Custom, pause/resume, watchdog or readback policy by guess.
