# RD6018 V3 canonical state

Status: architecture checkpoint, current at commit `87aa40d`.

This document is the portable source of truth for continuing V3 work in a new
session. It describes accepted boundaries and migration state; it is not an
authorization to enable START, ACTIVE, control, or physical execution.

## 1. Current architecture graph

```text
UI
 |
 v
Application
 |
 v
Domain
 |
 v
Execution Boundary
 |
 v
Infrastructure
 |
 +--> HA / ESP / RD

Cross-cutting:
  Configuration Authority
  Diagnostics
  Persistence
  Architecture Guardrails
```

Current V3 modules are contract/shadow boundaries. V2 remains the active
execution and physical owner. The production V3 route is not a second
production root.

## 2. Module ownership matrix

| Component | Current owner | Target owner | Migration mode | Rollback possibility |
|---|---|---|---|---|
| UI | V2 UI / shadow V3 adapter | V3 | staged | yes, V2 UI remains available |
| Telemetry | V3 staged authority; V2 source retained | V3 | mirror/staged | yes, `V2_ROLLBACK` telemetry view |
| Configuration | V3 `ConfigurationAuthority` / V2 effective view | V3 | shadow/staged | yes, V2 effective config view |
| Diagnostics | V3 `DiagnosticsDomain` with legacy consumers | V3 | mirror | yes, consumers remain unchanged |
| Persistence | V3 boundary; V2 stores remain | V3 | shadow | yes, no restore cutover |
| Domain decisions | V3 shadow domain; V2 active | V3 | shadow | yes, V2 remains active |
| Safety decisions | V2 safety owners | V3 | shadow | yes, V2 safety remains authoritative |
| Containment | V2/SafeOutput/lease owners | V3 logical policy candidate | shadow/staged | yes, existing containment path |
| Session | V2 session managers | V3 | shadow | yes, no session restore takeover |
| Execution | V2 transaction owner | V3 boundary delegating to approved owner | shadow | yes, V2 execution remains active |
| HA control | V2 | V3 | cutover only after approval | yes, explicit V2 control rollback |
| ESP control | V2/edge contract | V3 | cutover only after bench approval | yes, edge/V2 control retained |
| Physical output | V2/physical layer | V3 execution authority candidate | cutover only | yes, V2 physical owner remains |

The matrix is descriptive. No row performs an ownership transfer by being
listed here.

## 3. Migration history

| Stage | Commit(s) | Goal | Result |
|---|---|---|---|
| Architecture extraction, Phase 1–2.5 | `b5d05f5`, `b7a6240`, `77a0cfa` | inventory ownership, config/state drift, safety and actuator reachability | contracts, inventories and runtime graph documented; behavior unchanged |
| Containment/actuator preparation, Phase 3–4.4 | `bedbe7b`, `e48e7ba`, `c40754a`, `a163023`, `46a4236`, `d6193f4`, `8370701`, `013c363`, `0286101` | normalize observation and actuator contracts without execution | mappings, shadow adapters and parity contracts added; no physical wiring |
| Architecture extraction, Phase 5–6 | `80d9e0f`, `1313f70`, `9175255`, `57f6183`, `2703961`, `a1a1eb5`, `4420ca3`, `3f5d49e`, `c6b43a8`, `02c4301`, `45997c2` | extract domain, interfaces, persistence, composition, guardrails, config and diagnostics | pure contracts, validated config model and static boundaries established |
| Domain reconstruction, Phase 7 | `ffa449d`, `540c8d2` | implement and validate pure V3 domain runtime | domain skeleton and parity tests; production not connected |
| Application/execution boundaries, Phase 8 | `0e1bb69`, `520368d`, `c532d61`, `6a6edc7`, `c448563`, `153a4d3`, `6472fcf` | compose application, execution, UI, telemetry, persistence and shadow adapters | V3 shadow composition assembled; no production wiring |
| Shadow comparison, Phase 9 | `1e8c855`, `db42aaa` | compare V2/V3 decisions and explain divergence | comparison statuses and known conflict explanations |
| Production shadow, Phase 10 | `4a46d44`, `7bb56bf`, `6ca8ffb` | observe mirrored production inputs, retain evidence, define acceptance | observer, analytical evidence store and acceptance criteria |
| Ownership migration, Phase 11.0 | `0f1baea` | staged telemetry authority migration | V3 logical telemetry authority with V2 rollback view |
| Ownership migration, Phase 11.1 | `87aa40d` | staged configuration authority migration | V3 canonical config view with provenance/parity and V2 rollback |

These commits are the implementation trail on the current branch; later work
must preserve their non-authorizing boundaries.

## 4. Accepted architecture invariants

### UI

- does not call domain directly;
- does not know hardware;
- creates intents and presents results only.

### Domain

- does not import HA/ESP;
- does not execute physical actions;
- emits domain decisions and actuator-intent representations only.

### Telemetry

- read-only;
- does not make safety decisions;
- does not execute commands;
- retains source, freshness, confidence and provenance.

### Configuration

- `ConfigurationAuthority` is the canonical logical parameter source;
- all future configurable values must be represented through it;
- legacy YAML/Python/env sources are read-only migration inputs until retired.

### Safety

- remains a distinct module/authority;
- consumes configuration authority;
- is not mixed with transport adapters.

### Execution

- is the single actuator execution boundary;
- no UI, domain or telemetry adapter bypasses it.

### Persistence

- may produce restore candidates for validated domain state;
- does not directly restore actuator, lease or safety state;
- shadow evidence is analytical history, not restore state.

### Diagnostics

- observes and correlates facts;
- has no side effects;
- does not make safety or charge decisions.

## 5. Configuration migration state

| Source | Current state | Already moved | Still conflicting |
|---|---|---|---|
| YAML | validated read-only adapters and canonical model exist | manual, recipe/limits candidates, runtime/physical metadata provenance | duplicate limits, transport defaults, incomplete FLOODED recipe |
| Python constants | inventory and AST adapter exist | documented candidates for strategy/safety/readback | watchdog 180/300, Mix budgets, temperature and timeout literals |
| env | explicit read-only adapter and secret-name boundary exist | names/provenance only | deployment-specific lease/transport values and renewal source |
| runtime defaults | represented as candidates where known | typed model/validators | operation-specific readback, polling, settle and safety defaults |
| persisted state | ownership map and persistence boundary exist | candidate/analytical distinction | legacy session/manual/OFF/pause stores and recovery reconciliation |

No source has been silently deleted or made authoritative for production
execution by this checkpoint.

## 6. Known unresolved decisions

No independent choice is made here:

- EFB Mix 20 h vs 24 h;
- CC Delta/Vmax versus current-drop termination;
- Custom profile schema;
- pause/resume semantics;
- watchdog values;
- readback timeout policy.

## 7. Known V2 problems being corrected in V3

- monolithic bootstrap;
- hidden ownership;
- globals;
- coupled UI/runtime;
- mixed telemetry/control;
- multiple safety owners;
- transport leakage into logic;
- configuration drift.

V3 addresses these through explicit contracts and staged shadow evidence; it
does not remove V2 behavior without parity and approval evidence.

## 8. Migration roadmap by EPIC

### EPIC A — Canonical V3 baseline

**Goal:** keep the graph, ownership matrix, contracts, guardrails and config
authority internally consistent.

**Entry:** current shadow contracts and tests pass.

**Ready when:** no boundary contradiction, complete provenance and acceptance
criteria are reproducible.

**Rollback:** retain the current V2 production root and disable all shadow
consumers.

### EPIC B — Domain migration

**Goal:** prove V3 domain decisions against V2 over representative profiles,
phases, pause/resume and failure scenarios.

**Entry:** parity model and unresolved decisions are explicitly classified.

**Ready when:** approved shadow acceptance metrics pass with no unexplained
safety/containment divergence.

**Rollback:** V2 remains the decision owner; discard V3 candidate outputs.

### EPIC C — Infrastructure migration

**Goal:** make telemetry, configuration, diagnostics and persistence adapters
canonical without granting control authority.

**Entry:** staged telemetry/config ownership and source provenance are stable.

**Ready when:** arbitration, conflict detection, persistence candidate rules and
diagnostic evidence are complete.

**Rollback:** return telemetry/config views to V2 snapshots and retain evidence.

### EPIC D — Execution migration

**Goal:** prove V3 intent parity, rollback and verification at the execution
boundary without physical activation.

**Entry:** domain/infrastructure shadow acceptance and bench contracts pass.

**Ready when:** explicit operator, safety, rollback and physical-gate approvals
exist; no direct bypass remains.

**Rollback:** keep V2 transaction owner and reject V3 execution requests.

### EPIC E — Runtime cutover

**Goal:** perform a separately authorized, staged ownership transition.

**Entry:** all prior EPIC gates, exact deployment evidence and approved bench
procedure.

**Ready when:** explicit cutover approval exists for each authority, not merely
for the project as a whole.

**Rollback:** immediate return to V2 owner under verified containment and
operator reauthorization; never resume an ambiguous old session silently.

## 9. Future change rules

- do not create hidden owners;
- do not add globals;
- route every parameter through Configuration Authority;
- route every physical action through Execution Boundary;
- access every external data source through adapters;
- keep UI limited to intents;
- require every new module to declare an owner;
- add a boundary/static test and update this canonical state for every new
  migration capability;
- do not infer ownership transfer from a shadow result or a passing unit test.

## Checkpoint restrictions

This document does not change V2 runtime, V3 execution, START, ACTIVE, HA
control, ESP control or physical ownership.
