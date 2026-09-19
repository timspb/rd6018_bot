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

**Current status: shadow domain normalization.** The pure V3 FSM, profile,
strategy, session and safety contracts are documented and covered by domain
parity/comparison tests. V2 remains the decision, session, safety and execution owner. See `docs/RD6018_DOMAIN_MIGRATION_MODEL.md`.

Known blockers remain explicitly unresolved: EFB Mix 20 h versus 24 h, CC
Vmax/Delta-V versus current-drop, Custom profile schema, pause/resume
semantics, watchdog values and readback timeout policy.

**Entry:** parity model and unresolved decisions are explicitly classified.

**Ready when:** approved shadow acceptance metrics pass with no unexplained
safety/containment divergence.

**Rollback:** V2 remains the decision owner; discard V3 candidate outputs.

### EPIC C — Infrastructure migration

**Goal:** make telemetry, configuration, diagnostics and persistence adapters
canonical without granting control authority.

**Current status: shadow infrastructure normalization.** HA/ESP telemetry
adapters, deterministic arbitration, provenance/freshness, readback
observation, intent-only control and lease/failure taxonomy are documented and
tested as non-authoritative contracts. V2 remains the control, lease and physical owner.
See `docs/RD6018_INFRASTRUCTURE_MIGRATION_MODEL.md`.

**Entry:** staged telemetry/config ownership and source provenance are stable.

**Ready when:** arbitration, conflict detection, persistence candidate rules and
diagnostic evidence are complete.

**Rollback:** return telemetry/config views to V2 snapshots and retain evidence.

### EPIC D — Execution migration

**Goal:** prove V3 intent parity, rollback and verification at the execution
boundary without physical activation.

**Current status: contract/shadow execution preparation.** Typed intent
validation, owner checks, rollback/verification requirements, parity
classification and readiness gates are documented and tested. V2 remains the execution and physical owner. See `docs/RD6018_EXECUTION_MIGRATION_MODEL.md`.

**Entry:** domain/infrastructure shadow acceptance and bench contracts pass.

**Ready when:** explicit operator, safety, rollback and physical-gate approvals
exist; no direct bypass remains.

**Rollback:** keep V2 transaction owner and reject V3 execution requests.

### EPIC E — Runtime cutover

**Goal:** perform a separately authorized, staged ownership transition.

**Current status: runtime composition shadow shell.** `V3RuntimeComposition`
provides lifecycle, dependency validation, shadow workers, diagnostics and
health reporting around the existing V3 shadow graph. V2 remains the runtime and physical owner. See `docs/RD6018_RUNTIME_MIGRATION_MODEL.md`.

**Entry:** all prior EPIC gates, exact deployment evidence and approved bench
procedure.

**Ready when:** explicit cutover approval exists for each authority, not merely
for the project as a whole.

**Rollback:** immediate return to V2 owner under verified containment and
operator reauthorization; never resume an ambiguous old session silently.

### EPIC F — Dual runtime operation

**Current status: dual-runtime shadow coexistence.** V2 remains the production
execution owner. V3 may run only as an isolated shadow runtime with separate
namespaces, lifecycle cancellation and health reporting. See
`docs/RD6018_DUAL_RUNTIME_MODEL.md`.

### EPIC G — Decision ownership migration

**Current status: decision ownership shadow preparation.** V2 remains the
domain decision and execution owner. V3 compares and records shadow decisions
with explicit provenance; no implicit takeover or execution path exists. See
`docs/RD6018_DECISION_OWNERSHIP_MIGRATION_MODEL.md`.

### EPIC H.0 — Execution shadow validation

**Current status: execution shadow validation.** V3/V2 actuator parity,
safety/readback readiness and failure classification are validated as pure
data comparisons. No execution, transport write or ownership transfer is
enabled. See `docs/RD6018_EXECUTION_SHADOW_VALIDATION_MODEL.md`.

### EPIC H.1 — Long-running shadow acceptance

**Current status: long-running shadow observation.** V3 evidence is aggregated
into decision, execution, runtime, safety and configuration metrics with
PASS/WARNING/BLOCKED thresholds. The collector is observational and cannot
change ownership. See `docs/RD6018_LONG_RUNNING_SHADOW_ACCEPTANCE_MODEL.md`.

### EPIC I — Staged ownership cutover

**Current status: staged cutover model.** Stage 0–3 entry gates, health,
rollback, abort conditions and singular-owner invariants are defined as a
candidate model only. Live ownership remains unchanged. See
`docs/RD6018_STAGED_OWNERSHIP_CUTOVER_MODEL.md`.

### EPIC J — Decision cutover readiness

**Current status: Stage 1 readiness preparation.** Explicit approval,
safety-gate validation, provenance, rollback audit and decision-authority
observability are modeled without changing live ownership. See
`docs/RD6018_DECISION_CUTOVER_READINESS_MODEL.md`.

### EPIC K — Decision authority shadow run

**Current status: shadow rehearsal only.** V2 remains the live decision,
execution and physical owner. The V3 candidate flow, provenance, operator
history and rollback observation are modeled without dispatch or takeover. See
`docs/RD6018_DECISION_AUTHORITY_SHADOW_RUN_MODEL.md`.

### EPIC L — Decision cutover operational readiness

**Current status: operational preparation only.** Approval lifecycle,
emergency rollback visibility, audit trail and Stage 1 health gates are modeled
without enabling decision ownership. V2 remains the live decision, execution
and physical owner. See
`docs/RD6018_DECISION_CUTOVER_OPERATIONAL_READINESS_MODEL.md`.

### EPIC M — Decision canary controller

**Current status: decision-only canary model.** Bounded V3 decision authority,
expiry, blocker rollback, approval and audit state are modeled while V2 keeps
execution and physical ownership. See
`docs/RD6018_DECISION_CANARY_MODEL.md`.

### WORKSTREAM 2 — Boundary cleanup and decoupling

**Current status: partial cleanup; Stage 0 behavior preserved.** UI legacy
reads now use an explicit compatibility adapter, and safety/configuration/
actuator inventories are represented by non-executing contracts. Legacy domain
imports, production actuator bypasses, configuration conflicts, multiple V2/
edge safety owners and import-time V2 construction remain open. Architecture
PASS and Stage 1 are not approved. See
`docs/RD6018_BOUNDARY_CLEANUP_REPORT.md`.

### WORKSTREAM 2.1 — Legacy extraction and ownership cleanup

**Current status: adapter extraction and inventory complete; architecture PASS
still blocked.** V3-facing legacy domain imports now use an explicit adapter;
actuator paths, configuration decisions, safety ownership and lifecycle
contracts are inventoried without changing V2 behavior. Remaining B3/B4/B5/B6
risks are documented. See
`docs/RD6018_LEGACY_EXTRACTION_REPORT.md`.

### WORKSTREAM 2.2 — Execution safety runtime decoupling

**Current status: contract/inventory preparation only; Architecture PASS not
granted.** Actuator reachability, configuration completeness, safety decision
ownership and lifecycle/import risks are now represented by read-only contracts
and tests. B3 remains open because preserved V2 writers have not been routed
through the V3 dispatcher; B4 remains open because conflicting configuration
values are unresolved; B5 remains open because independent V2/edge safety
owners remain active; B6 remains open because V2 import-time construction was
not changed. Stage 1 and ownership transfer remain prohibited. See
`docs/RD6018_EXECUTION_SAFETY_RUNTIME_DECOUPLING_REPORT.md`.

### WORKSTREAM 3 — Legacy ownership separation

**Current status: inventory and adapter separation complete; Architecture PASS
not granted.** The named legacy domain adapter is now protected by forbidden
import tests; actuator ownership, configuration provenance, safety writers and
lifecycle are represented by canonical read-only maps. B3/B4/B5/B6 remain open
at the production level because V2 physical paths, unresolved values,
independent safety writers and V2 import-time construction were intentionally
not changed. Stage 0 remains PASS; Stage 1 remains disabled. See
`docs/RD6018_LEGACY_OWNERSHIP_SEPARATION_REPORT.md`.

### WORKSTREAM 4 — Controlled migration and legacy elimination

**Current status: standalone V3 core created; production migration blocked.**
The new `v3_core` package is independent of V2/legacy/infrastructure imports and
provides pure domain, safety, configuration, intent, shadow execution and one
standalone composition root. It is not connected to production and performs no
physical commands. V2 remains behavior/parity reference only for this slice;
legacy physical paths were not removed because exact actuator/readback/rollback
and ESPHome bench validation is still required. See
`docs/RD6018_CONTROLLED_MIGRATION_REPORT.md`.

### WORKSTREAM 5 — V3 physical boundary validation

**Current status: validation models PASS; physical boundary NOT VALIDATED.**
Capability, readback, lease-parity and safety-to-physical contracts are now
covered by non-actuating tests. No real adapter, hardware transport, lease
operation or physical command was connected. V2 and ESPHome ownership remain
unchanged; production readiness is blocked pending exact adapter/readback/
rollback parity and supervised bench evidence. See
`docs/RD6018_V3_PHYSICAL_BOUNDARY_VALIDATION_REPORT.md`.

### WORKSTREAM 6 — V3 physical adapter implementation and bench isolation

**Current status: `PHYSICAL_ADAPTER_READY` for isolated bench contract only.**
`v3_core.V3PhysicalAdapter` implements translation, injected in-memory transport,
readback verification, containment/rollback intent and dispatcher routing. It
has no HA/ESPHome/real hardware implementation and is not wired into
production. Production readiness, cutover and physical ownership remain
blocked pending exact adapter/lease parity and supervised bench authorization.
See `docs/RD6018_V3_PHYSICAL_ADAPTER_MODEL.md`.

### WORKSTREAM 7 — Lease, safety and real-transport parity validation

**Current status: parity models implemented; production parity `BLOCKED`.**
V3 safety trigger ownership, lease scenarios, transport failure states,
telemetry failure decisions, restart recovery and bench matrix are covered by
non-physical tests. The exact ESPHome/RD target contract has not been exercised;
V2/HA/ESPHome/lease ownership and physical output remain unchanged. See
`docs/RD6018_SAFETY_TRANSPORT_PARITY_VALIDATION_REPORT.md`.

### WORKSTREAM 8 — V3 UI session timeline and visualization normalization

**Current status: `UI_SESSION_MODEL_READY` for the pure V3 presentation
contract.** Session-scoped view models, timeline events, graph buffers,
operator filtering and explicit empty/fault states are implemented without
domain/runtime/execution imports. V2 UI and runtime are unchanged; no physical
or ownership path is involved. See
`docs/RD6018_UI_SESSION_TIMELINE_MODEL.md`.

### WORKSTREAM 9 — V3 operator observability and diagnostics

**Current status: `OPERATOR_OBSERVABILITY_READY` for the pure V3 contract.**
`DiagnosticsDomain`, `TraceContext`, health snapshots, dashboard read models,
operator alerts and history queries are implemented without UI callbacks,
runtime side effects or physical access. V2 runtime and all ownership paths are
unchanged. See `docs/RD6018_OPERATOR_OBSERVABILITY_MODEL.md`.

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

## WORKSTREAM 10 — External integration parity validation

**Current status: BLOCKED for external parity acceptance.**

V3 now contains non-connecting parity models for ESPHome, HA, lease scenarios,
telemetry arbitration, external readback, failure classification, and operator
diagnostics. These models are comparison/shadow contracts only. The target
external contour was not contacted; V2 runtime, HA/ESPHome/lease ownership and
physical output remain unchanged. See
`docs/RD6018_EXTERNAL_INTEGRATION_PARITY_REPORT.md`.

## WORKSTREAM 11 — Hardware validation and controlled integration readiness

**Current status: BLOCKED.**

Read-only real-contour validation models and no-write tests are prepared for
telemetry, readback, ESPHome, HA, lease observation and V2/V3 shadow comparison.
No external contour was contacted and no physical or lease command was issued.
V2 remains production/physical owner. See
`docs/RD6018_REAL_HARDWARE_VALIDATION_REPORT.md`.

## WORKSTREAM 12 — Live shadow evidence collection

**Current status: BLOCKED.**

The in-memory, read-only shadow evidence collector is prepared for timestamped
telemetry/readback/session/lease observations, trace correlation, divergence
classification and operator dashboard counts. No live installation was
contacted; no evidence is represented as collected, and V2 remains the
production/physical owner. See
`docs/RD6018_LIVE_SHADOW_EVIDENCE_REPORT.md`.

## WORKSTREAM 13 — Live shadow observation run

**Current status: BLOCKED.**

The controlled observation lifecycle and evidence bundle are implemented for
real timestamped source snapshots, session timelines, V2/V3 comparisons, UI
checks and diagnostics. No live installation was contacted in this run, so no
runtime evidence is claimed as collected. V2 remains production/physical owner.
See `docs/RD6018_LIVE_SHADOW_OBSERVATION_RUN_REPORT.md`.

## WORKSTREAM 14 — Controlled live observation execution

**Current status: BLOCKED.**

The first authenticated HA read-only snapshot was collected using the existing
V2 token from node 101. No write, control, lease or physical action was
executed. The run remains blocked for full parity because direct ESPHome
observation, V3 trace correlation and a coherent current session timeline are
missing. See
`docs/RD6018_CONTROLLED_LIVE_OBSERVATION_REPORT.md`.

## WORKSTREAM 14.1 — Live state consistency investigation

**Current status: STATE_CONSISTENCY_VALIDATED with observability warning.**

The apparent STOP/active contradiction was resolved: `stop_reason` is historical
Main-to-Mix metadata, while the persisted lifecycle is `active`; systemd
journal confirms `stopped -> cooling -> arming -> active`. Physical Output ON
and CC therefore match the current Mix state. Manual lifecycle evidence is
split between journal and coarse charging history, and `EMERGENCY_UNAVAILABLE`
has insufficient source context to infer an active safety condition. See
`docs/RD6018_LIVE_STATE_CONSISTENCY_REPORT.md`.

## WORKSTREAM 14.2 — Canonical event timeline normalization

**Current status: CANONICAL_EVENT_TIMELINE_READY.**

V3 now has a pure canonical event taxonomy, typed reason model, source/activity
classification, normalizer and UI timeline snapshot contract. Journal, legacy
history and persisted data remain unchanged; no runtime or ownership path was
modified. See `docs/RD6018_CANONICAL_EVENT_TIMELINE_MODEL.md`.

## WORKSTREAM 15 — V3 shadow runtime evidence aggregation

**Current status: SHADOW_EVIDENCE_AGGREGATION_READY.**

V3 has a pure evidence bundle, correlation validator, replay view and isolated
analytical namespace. Replay cannot execute commands or restore runtime state;
the dashboard shadow status is optional and backward-compatible. No ownership or
physical path changed. See
`docs/RD6018_SHADOW_RUNTIME_EVIDENCE_AGGREGATION_MODEL.md`.

## WORKSTREAM 17 — Canary preflight validation

**Current status: CANARY_PREFLIGHT_READY as a gate; activation remains BLOCKED.**

The read-only `CanaryPreflightValidator` evaluates readiness, health, shadow
evidence freshness, diagnostics, approval, rollback and blocker registry. It
does not activate Canary or transfer authority. See
`docs/RD6018_CANARY_PREFLIGHT_VALIDATION_MODEL.md`.

## WORKSTREAM 16 — V3 canary readiness and migration gate

**Current status: CANARY_READINESS_DEFINED; activation BLOCKED.**

The formal readiness matrix, entry criteria, modes, rollback triggers, approval
gate and blocker taxonomy are defined. This is a non-activating gate: no canary,
authority transfer, lease takeover or physical execution occurred. See
`docs/RD6018_V3_CANARY_READINESS_MODEL.md`.
## WORKSTREAM 18 — Canary preflight live evaluation

**Current status: `CANARY_PREFLIGHT_LIVE_EVALUATED — CANARY_BLOCKED`.**

15 September 2026 проведена read-only оценка фактического состояния через HA на 102. V2 остался production owner; V3 не получил authority и не выполнял commands, writes, lease operations или physical execution. Свежая HA/RD telemetry наблюдалась, но Canary gate заблокирован отсутствующим approval, устаревшими lease safety indicators, неполной ESPHome/RD direct parity и отсутствующей полной свежей V3 shadow evidence chain. Подробности: `docs/RD6018_CANARY_PREFLIGHT_LIVE_EVALUATION_REPORT.md`.
## WORKSTREAM 19 — Canary blocker resolution planning

**Current status: `CANARY_BLOCKERS_CLASSIFIED`; Canary remains `CANARY_BLOCKED`.**

Активные blockers из live preflight классифицированы по категориям Approval, Safety, External, Operational и Execution. Созданы read-only registry, resolution plan и operator snapshot contract. Approval не создавался, lease/ownership/physical execution не изменялись. См. `docs/RD6018_CANARY_BLOCKER_RESOLUTION_PLAN.md`.
## WORKSTREAM 20 — Shadow evidence chain completion

**Current status: `BLOCKED`; `CB-EVIDENCE-001` remains OPEN.**

Minimum chain validator and replay-only tests готовы, но свежая complete V3 shadow chain не подтверждена. Synthetic chain используется только для тестов; доступный HA-only пакет не доказывает START-to-STOP canonical events, full telemetry correlation и прямую ESPHome parity. См. `docs/RD6018_SHADOW_EVIDENCE_CHAIN_COMPLETION_REPORT.md`.
## WORKSTREAM 21 — Direct evidence source enablement

**Current status: `BLOCKED`; `CB-EVIDENCE-001` remains OPEN.**

Подготовлены read-only ESPHome evidence contract, trace correlation validator, runtime event source inventory и raw-to-canonical reassembly. Live direct ESPHome/API evidence и полная V3 trace/session chain не подтверждены; ownership и physical execution не изменялись. См. `docs/RD6018_DIRECT_EVIDENCE_SOURCE_ENABLEMENT_REPORT.md`.
## WORKSTREAM 21 live source result

Read-only live check подтвердил оба внешних источника: HA `192.168.1.102` и ESPHome `192.168.1.28:6053`; основные RD telemetry/readback values согласованы, lease direct state наблюдается. Source enablement: `DIRECT_EVIDENCE_SOURCES_READY`. Полная V3 event chain и trace/session correlation ещё не доказаны, поэтому `CB-EVIDENCE-001` остаётся OPEN/BLOCKED. Ownership и physical execution не изменялись.
## WORKSTREAM 22 — Live charge cycle evidence capture

**Current status: `BLOCKED`; `CB-EVIDENCE-001` remains OPEN.**

Текущая V2-owned сессия `Baic72/MIX` и согласованная HA/ESPHome telemetry обнаружены read-only, но persisted session не содержит `session_id`, а полная START-to-STOP canonical event chain отсутствует. Добавлены observer/replay contracts; physical/control/lease paths не затрагивались. См. `docs/RD6018_LIVE_CHARGE_CYCLE_EVIDENCE_REPORT.md`.
## WORKSTREAM 23 — Session identity & event correlation

**Current status: `SESSION_CORRELATION_READY`; `CB-EVIDENCE-001` remains OPEN/BLOCKED.**

Добавлены observer-only identity/resolver/reconstruction contracts с запретом угадывать ambiguous events и смешивать historical/current timeline. V2 runtime, FSM, ownership и physical paths не изменялись. См. `docs/RD6018_SESSION_IDENTITY_CORRELATION_MODEL.md`.
## WORKSTREAM 24 — Session birth observation

**Current status: `BLOCKED`; `SESSION_BIRTH_CAPTURED` не подтверждён.**

Добавлен read-only observer для idle→active boundary и identity validation. Текущая V2-сессия уже была active/MIX, поэтому START не инициировался и не был приписан задним числом. См. `docs/RD6018_SESSION_BIRTH_OBSERVATION_REPORT.md`.
## WORKSTREAM 25 — Active session identity gap

**Current status: `SESSION_IDENTITY_GAP_IDENTIFIED`; `CB-EVIDENCE-001` remains OPEN/BLOCKED.**

Аудит подтвердил разрыв между automatic V2 trace identity и managed Manual path: `manual_session_v2.json` не содержит `session_id/trace_id`, а Manual restore их не создаёт. Runtime/FSM/persistence/physical paths не изменялись. См. `docs/RD6018_ACTIVE_SESSION_IDENTITY_GAP_REPORT.md`.
## WORKSTREAM 26 — Manual session identity boundary

**Current status: `MANUAL_IDENTITY_BOUNDARY_DEFINED`; `CB-EVIDENCE-001` remains OPEN/BLOCKED.**

Созданы design-only contracts для Manual identity и event bridge. Restore без полной identity не угадывается и получает `AMBIGUOUS`; V2 runtime/FSM/physical paths не подключались. См. `docs/RD6018_MANUAL_SESSION_IDENTITY_BOUNDARY_MODEL.md`.

## WORKSTREAM 27 — Manual identity runtime observation

**Current status: `BLOCKED`; `MANUAL_IDENTITY_RUNTIME_VALIDATED` не подтверждён.**

Observer-only contract подготовлен, но `ProductionManualSessionManager` не подключает identity boundary и не выдаёт identity-bearing canonical events. V2 остаётся production owner; V3 не получил control/lease/physical authority. См. `docs/RD6018_MANUAL_IDENTITY_RUNTIME_OBSERVATION_REPORT.md`.

## WORKSTREAM 28 — Manual identity boundary integration

**Current status: `MANUAL_IDENTITY_INTEGRATION_READY`; `CB-EVIDENCE-001` remains OPEN pending live capture.**

`ProductionManualSessionManager` получил минимальный identity adapter: новые Manual starts создают lifecycle identity, complete persisted identity восстанавливается, legacy state без identity остаётся `AMBIGUOUS`, а canonical events доступны downstream evidence consumers. Charge/FSM/physical/lease behavior и V2 ownership не менялись. См. `docs/RD6018_MANUAL_IDENTITY_INTEGRATION_REPORT.md`.

## WORKSTREAM 29 — First real Manual identity evidence capture

**Current status: `BLOCKED`; `CB-EVIDENCE-001` remains OPEN.**

Replay-only collector готов, но новая V2-owned Manual сессия и полная correlated chain в observation window не получены. Старая session и synthetic events не засчитывались; control, lease и physical ownership не менялись. См. `docs/RD6018_FIRST_MANUAL_IDENTITY_EVIDENCE_REPORT.md`.

## WORKSTREAM 30 — Active session V3 runtime parity

**Current status: `ACTIVE_SESSION_PARITY_READY`; `CB-EVIDENCE-001` remains OPEN for full lifecycle evidence.**

V3 shadow теперь может принимать уже активную Manual-сессию без искусственного START/STOP. Отсутствующая legacy identity классифицируется `LEGACY_NO_IDENTITY`; профиль, MIX phase, state и telemetry сравниваются с V2 current view. Control, lease и physical ownership не менялись. См. `docs/RD6018_ACTIVE_SESSION_V3_PARITY_REPORT.md`.

## WORKSTREAM 31 — V3 operator runtime integration

**Current status: `OPERATOR_RUNTIME_READY`; V2 remains production owner.**

Read-only operator composition объединяет telemetry, active-session parity,
current-session timeline, diagnostics и shadow evidence. Control surface явно
disabled; чужая timeline или legacy identity не получают fake START. См.
`docs/RD6018_OPERATOR_RUNTIME_INTEGRATION_MODEL.md`.

## WORKSTREAM 32 — V3 operator diagnostics and decision explanation

**Current status: `OPERATOR_EXPLANATION_READY`; V2 remains production owner.**

Добавлен read-only explanation layer для decision/phase/safety facts. Missing
evidence получает `UNKNOWN`, historical faults отделены от active safety, а
V2/V3 comparison сохраняет `MATCH/EXPECTED_DIFFERENCE/UNKNOWN`. См.
`docs/RD6018_OPERATOR_DECISION_EXPLANATION_MODEL.md`.

## WORKSTREAM 33 — V3 operator dashboard composition

**Current status: `OPERATOR_DASHBOARD_READY`; V2 remains production owner.**

Единый immutable dashboard snapshot объединяет current session, timeline,
telemetry, explanation, safety, diagnostics, parity и Canary readiness. Панели
не читают источники независимо; degraded/unknown данные не угадываются.
Dashboard остаётся observe-only. См.
`docs/RD6018_OPERATOR_DASHBOARD_COMPOSITION_MODEL.md`.

## WORKSTREAM 34 — Telegram operator view adapter

**Current status: `TELEGRAM_OPERATOR_VIEW_READY`; V2 remains production owner.**

Telegram formatter принимает только `OperatorDashboardState`, показывает
current-session observations, explanations, safety/diagnostics и parity. Direct
HA/ESP/history/runtime reads и command handlers отсутствуют; control явно
недоступен. См. `docs/RD6018_TELEGRAM_OPERATOR_ADAPTER_MODEL.md`.

## WORKSTREAM 35 — V3 observer composition integration

**Current status: `V3_OBSERVER_COMPOSITION_READY`; V2 remains production owner.**

Единый observer composition root соединяет read-only sources, telemetry,
active-session parity, explanation, dashboard и Telegram formatter. Lifecycle
идемпотентен, degraded readers дают `UNKNOWN`; command/lease/physical
dependencies отсутствуют. См. `docs/RD6018_V3_OBSERVER_COMPOSITION_MODEL.md`.

## WORKSTREAM 36 — V3 observer live run validation

**Current status: `BLOCKED`; fresh live observer validation не подтверждена.**

Composition-to-Telegram pipeline и degraded behavior проверены локально, но в
текущем workspace отсутствуют штатные `HA_TOKEN`/`ESPHOME_API_KEY`; свежий HA
HTTP/API и ESPHome Native API snapshot не получен. Старые snapshots не выданы
за live evidence. См. `docs/RD6018_V3_OBSERVER_LIVE_RUN_VALIDATION_REPORT.md`.

## WORKSTREAM 37 — Live observer secret boundary verification

**Current status: `BLOCKED`; deployment secret presence is not available in the workspace.**

Создан presence-only configuration check для штатного service environment на
deployment host. Он не выводит значения секретов, требует оба reader secret и
фиксирует `read-only/writes_allowed=false`. См.
`docs/RD6018_LIVE_OBSERVER_CONFIGURATION_BOUNDARY_REPORT.md`.

## WORKSTREAM 38 — Deployment live observer validation

**Current status: `BLOCKED`; deployment live snapshot не получен.**

Проверка node 101 остановилась на SSH authentication boundary: в текущем
окружении нет SSH executable и Paramiko не нашёл ключ/agent. Service restart,
Telegram polling, commands, lease и physical execution не выполнялись. См.
`docs/RD6018_DEPLOYMENT_LIVE_OBSERVER_VALIDATION_REPORT.md`.

## WORKSTREAM 39 — Deployment access recovery

**Current status: `ACCESS_READY`; read-only access to the штатные deployment
sources is restored.**

Сохранённая WinSCP-сессия дала read-only доступ к node 101 и HA node 102.
На 101 сервис `rd6018-bot.service` активен, `.env` содержит `HA_TOKEN`.
На 102 найден ESPHome secret `rd6018_api_encryption_key`; Native API
`192.168.1.28:6053` подтвердил подключение и 66 entities. Команды, записи,
перезапуск, lease operations и ownership changes не выполнялись. Повтор
Workstream 38 теперь разблокирован, но отдельная V3 observer validation ещё
не считается выполненной. См.
`docs/RD6018_DEPLOYMENT_ACCESS_RECOVERY_REPORT.md`.

## WORKSTREAM 36 R2 — V3 observer live run validation (deployment environment)

**Current status: `BLOCKED`; live sources are healthy, but V3 observer
composition is not present on deployed HEAD `10af870`.**

Read-only HA/ESPHome/RD checks passed and a local observer contract rendered
the current `Baic72 / mix / active` state. The deployed node lacks the V3
observer modules, so this is not yet a deployment-runtime validation. No
restart, write, command, lease operation or ownership change was made. См.
`docs/RD6018_V3_OBSERVER_LIVE_RUN_VALIDATION_R2_REPORT.md`.

## WORKSTREAM 42 — V2 functional audit before control migration

**Current status: `FUNCTIONAL_PARITY_AUDIT_COMPLETE`; control migration remains
blocked by documented V2 parity/configuration gaps.**

Read-only inventory completed for V2 safety, FSM/charge algorithms, logs and
event loss, restart/restore behavior, and battery/profile binding. Key open
findings are EFB Mix `20 h` code versus accepted `24 h` documentation, watchdog
`180 s` versus `300 s` constants, distributed voltage limits, and incomplete
universal event identity. No runtime or physical behavior changed. См.
`docs/RD6018_V2_FUNCTIONAL_AUDIT_REPORT.md`.

## WORKSTREAM 41 — V3 UI timeline quality pass

**Current status: `UI_TIMELINE_QUALITY_READY`.**

В development tree добавлены явные timeline display entries для event time,
phase, reason и condition, session filtering, graph reset validation и
`UNKNOWN`-семантика для отсутствующих событий/evidence. Новые и регрессионные
UI-тесты прошли. Deployment, production runtime, FSM, START/STOP, lease и
physical execution не менялись. См.
`docs/RD6018_UI_TIMELINE_QUALITY_REPORT.md`.

## WORKSTREAM 49 — V3 legacy contamination cleanup

**Current status: `V3_CONTAMINATION_CLEAN`.**

Resolver selection is separated from the program catalog, the V3 charge engine
has one generic implementation, chemistry aliases are isolated to an input
mapping, and the pure core import guardrails pass. V2 runtime, production
composition, deployment and physical execution were not connected. См.
`docs/RD6018_V3_LEGACY_CONTAMINATION_CLEANUP_REPORT.md`.
