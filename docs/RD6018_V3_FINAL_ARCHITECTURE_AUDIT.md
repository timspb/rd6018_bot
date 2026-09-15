# RD6018 V3 Final Architecture Audit — WORKSTREAM 1

Audit mode: read-only. No runtime, ownership, execution, START, ACTIVE, HA,
ESPHome, lease or physical state was changed.

Audit basis:

- `docs/RD6018_V3_CANONICAL_STATE.md`;
- all tracked `docs/RD6018_*_MODEL.md` documents;
- `docs/RD6018_ARCHITECTURE_GUARDRAILS.md`;
- `docs/RD6018_CONFIGURATION_MIGRATION_INVENTORY.md`;
- static AST/import/call-site inspection of `application/`, `runtime/`,
  `bot.py` and the V2 compatibility modules;
- existing architecture and migration tests.

## Executive result

**Status: NOT READY FOR REAL OWNERSHIP TRANSITIONS.**

The pure V3 contracts and shadow decision/canary models are structurally
isolated. The repository as a whole still contains known transitional coupling
and multiple production actuator/safety paths. This is consistent with the
canonical state that V2 remains the live owner, but it blocks Stage 1+ until
the findings below are resolved with parity evidence.

### Blockers

| ID | Finding | Evidence | Impact |
|---|---|---|---|
| `ARCH-B01` | UI/application presentation still imports live/legacy infrastructure | `application/operator_snapshot_provider.py` imports `operator_hmi`, `rd6018_telemetry`, `runtime.diagnostics`, `runtime.journal` | UI boundary is not fully isolated; infrastructure ownership can leak into presentation |
| `ARCH-B02` | V3 shadow composition directly imports the runtime charge package | `application/shadow_composition.py` imports `runtime.charge` | Domain boundary is transitional rather than adapter-only |
| `ACT-B01` | V3 `ExecutionDispatcher` is not the only actuator path in the repository | `runtime/v2_runtime.py`, `v2_startup.py`, `manual_mode.py`, `runtime_safety*.py`, `safe_output.py`, `edge_safety_lease.py` remain reachable production owners | No safe execution ownership cutover can occur while bypasses remain |
| `CFG-B01` | Configuration authority is incomplete and conflicting sources remain | configuration migration inventory; Python literals and YAML/env/persisted-state duplicates | Decisions cannot be reproduced from one canonical snapshot |
| `SAFE-B01` | Multiple safety/containment owners remain by design | runtime watchdogs, `runtime_safety*`, `SafeOutputCoordinator`, edge lease and ESPHome dead-man | Must preserve V2/edge behavior until containment and verification parity is proven |
| `RUN-B01` | V2 module import has module-level runtime construction and multiple background paths | `runtime/v2_runtime.py` constructs Telegram/HA globals at import; soft/hard watchdog and lifecycle paths exist | Hidden startup/resource coupling prevents claiming a single clean V3 runtime root |

## 1. Module isolation audit

### Verified boundaries

The following pure V3 contract groups passed static forbidden-import checks:

- decision comparison, authority shadow, readiness and canary models;
- ownership/cutover models;
- diagnostics domain;
- persistence boundary;
- data-only actuator/containment contracts.

They do not import HA, ESPHome, transport clients, controllers, lease
implementations or physical output adapters, and their tests reject direct
actuator calls.

### Transitional coupling found

| Boundary | Result | Finding |
|---|---|---|
| Domain → Infrastructure | `WARN/BLOCKER` for whole graph | `application/charge_orchestration.py` and `shadow_composition.py` import `runtime.charge`; this is a transitional V3-to-domain dependency, not a transport write |
| UI → Hardware/Infrastructure | `BLOCKER` for strict target boundary | `operator_snapshot_provider.py` reads legacy HMI/telemetry/journal/diagnostics modules |
| Configuration → code | `BLOCKER` for completeness | `ConfigurationAuthority` exists, but `runtime/v2_runtime.py` and legacy strategy/safety modules still own literals |
| Diagnostics → side effects | `PASS` for `application/diagnostics_domain.py`; `WARN` for legacy consumers | pure factory is data-only; legacy runtime diagnostics remain outside the pure boundary |
| Persistence → runtime | `PASS` for V3 boundary; `WARN` for production state | V3 restore candidates are non-authorizing, but V2 session/manual/OFF/pause stores remain active |
| Execution Boundary → actuator path | `BLOCKER` globally | boundary is pure/shadow; existing V2 physical callers remain reachable |

## 2. Ownership audit

| Authority | Current owner | Backup/rollback owner | Duplicate/ambiguity | Status |
|---|---|---|---|---|
| Telemetry | V3 staged arbitrator with V2 source retained | V2 snapshot/view | shared consumers and source arbitration | `STAGED` |
| Configuration | V3 canonical view; V2 effective runtime | V2 effective view | YAML/Python/env/runtime defaults/persisted state drift | `BLOCKED` |
| Diagnostics | V3 diagnostic contracts plus legacy consumers | legacy diagnostic paths | mirror consumers | `MIRROR` |
| Persistence | V3 boundary for candidates/evidence; V2 stores active | V2 stores | multiple session/manual/OFF/pause readers/writers | `BLOCKED` |
| Domain | V3 shadow domain; V2 active charge runtime | V2 | dual calculation is intentional shadow, not dual active owner | `SHADOW` |
| Decision | V2 live; V3 shadow/canary candidate only | V2 | canary model is not wired to production | `SHADOW` |
| Safety/containment | V2 runtime safety, SafeOutput, manual paths, edge dead-man | V2/edge fail-safe | multiple trigger owners by design; final physical boundary must remain singular per transaction | `BLOCKED` |
| Execution | V2 transaction/runtime | V2 rollback | V3 dispatcher is shadow-only, not production owner | `V2` |
| Lease | ESPHome/edge dead-man with V2 renewal/control contract | edge fail-safe | Python renewal and edge expiry are separate authorities and need exact contract evidence | `BLOCKED` |
| Physical output | V2 physical layer; ESPHome local dead-man as final protection | V2/edge fail-safe | independent edge authority is intentional, but no V3 takeover is allowed | `V2` |

There is no approved dual *active* owner for decision or execution. The
telemetry/configuration/diagnostics rows are explicitly migration states, not
permission to perform a cutover.

Operational invariant: **V2 remains execution owner and V2 remains physical
owner** until a separately approved cutover closes all blockers.

## 3. Hidden coupling audit

### Confirmed risks

- `runtime/v2_runtime.py` creates Telegram runtime, dispatcher/router and HA
  client as module globals; importing the module is therefore not side-effect
  free.
- `bot.py` performs top-level installer composition and creates an authority
  reconciliation task from its production `main()`; `bot_legacy.py` remains a
  rollback-only alternate entrypoint.
- V2 has distinct soft watchdog, hardware watchdog, lifecycle and dashboard/
  notification task paths. Their ownership is documented, but not collapsed
  into one V3 worker registry.
- V3 `runtime_composition.py` owns shadow worker tasks only; it is not a second
  production root, but this must remain statically enforced.
- Persisted session, manual session, manual OFF, operator pause and RD control
  mode are separate state surfaces with different lifetimes.

### No evidence found in the V3 contract layer

No new `asyncio.run(main())`, physical client construction, or actuator writer
was found in the pure V3 contract/canary modules. This does not prove runtime
reachability safety for legacy modules.

## 4. Configuration audit

The Phase 6.4 model covers candidates for charge, strategy, safety,
containment, lease, execution, transport, UI and persistence, but it is not yet
a complete replacement for runtime values.

### Confirmed complete as a typed candidate

- manual main voltage/current;
- manual mix hold;
- strategy mix hold;
- outer voltage/current/temperature limits;
- containment poll/grace;
- lease TTL;
- readback timeout;
- telemetry interval and HA timeout;
- dashboard refresh;
- session file reference.

### Still conflicting or incomplete

- EFB Mix budget 20 h versus 24 h;
- watchdog 180 s versus 300 s;
- readback/settle windows 5/10/15 s and operation-specific polls;
- temperature warning/pause/critical literals absent from canonical YAML;
- automatic/manual Delta and hold semantics in multiple units;
- OVP/OCP margin values with different contexts;
- transport default/priority disagreement;
- lease renewal source/interval not represented by one tracked canonical value;
- incomplete FLOODED profile and unresolved Custom schema;
- persisted runtime state still participates in effective behavior.

Configuration status: **CONFLICT / NOT READY FOR AUTHORITY CUTOVER**. No value
was selected or rewritten by this audit.

## 5. Safety audit

### Present protections

- V2 transactional output enable and SafeOutput containment;
- V2 watchdog and runtime safety wrappers;
- positive OFF/readback semantics where the path supports them;
- independent ESPHome/edge dead-man lease;
- typed containment result and observation contracts;
- persistence rules rejecting direct restore of actuator, lease or safety state;
- rollback models preserving V2 decision/execution/physical ownership.

### Risks requiring closure

- containment has multiple requesters and must retain one verified physical
  boundary per transaction;
- Python emergency paths and edge dead-man timing/authority must be proven
  together, not normalized by a model document;
- readback timeout and OFF confirmation semantics are not one canonical policy;
- lease renewal, expiry observation and containment relation require exact
  Python/ESPHome contract evidence;
- V3 safety remains recommendation/shadow data and is not allowed to suppress
  V2 safety actions.

## 6. Runtime audit

| Area | Current evidence | Result |
|---|---|---|
| Startup | `bot.py` is the production entrypoint; `bot_legacy.py` is rollback-only; top-level installers remain | `WARN`, one production marker but transitional import coupling |
| Shutdown | V2 lifecycle plus safety/containment paths; V3 shell cancels only its own shadow tasks | `WARN`, cancellation ownership is split by runtime |
| Restart | V2 startup recovery and persisted state reconciliation exist | `WARN/BLOCKER` until state ownership and reauthorization are fully evidenced |
| Workers | V2 watchdog/lifecycle/dashboard tasks; V3 injected shadow workers | `WARN`, duplicate-worker risk requires runtime inventory/evidence |
| Cancellation | V3 shell has explicit cancellation; V2 paths have independent task lifecycles | `WARN` |
| Health | V3 `RuntimeHealth`/dual-runtime health exists; V2 health remains external/legacy | `SHADOW` |

No runtime lifecycle was changed by this audit.

## 7. Migration readiness by stage

| Stage | Readiness | Reason |
|---|---|---|
| Stage 0 — V2 current / V3 shadow | `PASS` | Current documented and tested operating model; V2 remains owner |
| Stage 1 — V3 decision / V2 execution | `BLOCKED` | `ARCH-B01`, `CFG-B01`, `SAFE-B01` and unresolved parity/config conflicts remain |
| Stage 2 — V3 execution boundary / V2 fallback | `BLOCKED` | `ACT-B01`, readback/rollback parity and physical bench evidence incomplete |
| Stage 3 — full ownership | `BLOCKED` | Requires Stage 2, exact lease/ESPHome validation, physical bench gate and verified rollback |

## 8. Technical debt register

1. Retire or isolate `operator_snapshot_provider.py` legacy infrastructure
   reads behind explicit adapters.
2. Remove V3 shadow composition's direct dependency on legacy runtime domain
   package after domain parity is complete.
3. Inventory and converge all actuator writers behind the approved V2 boundary
   before any V3 execution cutover.
4. Resolve configuration conflicts without inventing values; encode provenance
   and units in the canonical model.
5. Define one state ownership map for session/manual/OFF/pause/recovery files.
6. Prove watchdog, readback and lease timing against the exact ESPHome contract.
7. Replace import-time V2 construction with an explicitly audited composition
   boundary only in a separately authorized runtime migration.

## 9. Recommendations and exit criteria

Recommended order:

1. close module-isolation blockers;
2. finish configuration conflict inventory and parity vectors;
3. map every production actuator call and prove no bypass remains;
4. reconcile state/worker/restart ownership;
5. run long shadow evidence with zero unexplained safety conflicts;
6. only then request a separately approved Stage 1 canary.

Workstream 1 exit status: **AUDIT COMPLETE, CUTOVER NOT APPROVED**.

## Restrictions confirmed

This audit did not change V2 runtime, START, ACTIVE, HA, ESPHome, lease
ownership, physical ownership, configuration values or execution behavior.
