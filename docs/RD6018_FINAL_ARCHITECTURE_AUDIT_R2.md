# RD6018 Final Architecture Audit R2

Режим: read-only audit. Runtime, ownership, START/ACTIVE, HA, ESPHome, lease и
physical execution не изменялись.

## 1. Executive result

**Stage 0: PASS — unchanged and preserved.**

V2 остаётся live decision/execution/physical owner. V3 работает только через
shadow/contracts. После Workstream 2.1 и 2.2 границы стали более явными, но
production architecture PASS и Stage 1 **не достигнуты**.

| Area | R2 status | Stage 1 effect |
|---|---|---|
| Module isolation | WARNING | transitional adapters remain |
| Ownership map | BLOCKED | no singular migration-ready safety/execution owner |
| Actuator graph | BLOCKED | V2 physical bypasses remain reachable |
| Configuration authority | BLOCKED | conflicts and literals remain |
| Safety ownership | BLOCKED | several independent physical safety writers remain |
| Runtime lifecycle | BLOCKED | V2 import-time construction/workers remain |

## 2. Module isolation

### UI

**WARNING.** `application/operator_snapshot_provider.py` no longer imports
legacy infrastructure directly; it uses
`application/legacy_ui_boundary.py`. The adapter still reads
`operator_hmi`, `rd6018_telemetry`, `runtime.diagnostics` and `runtime.journal`.
This is an explicit compatibility seam, not full isolation from infrastructure.

Required migration: replace the compatibility read adapter with a stable UI
query port backed by an application/infrastructure adapter, then prove no UI
module can reach live clients or physical methods.

### Domain

**WARNING.** `application/charge_orchestration.py` and
`application/shadow_composition.py` use `application/legacy_domain_adapter.py`;
that adapter imports `runtime.charge`. Direct leakage was reduced, but V3
domain logic is not yet independent of the legacy package.

Required migration: complete parity-backed domain extraction and remove the
legacy domain adapter from V3 composition.

### Infrastructure

**PASS for pure V3 contracts; WARNING for whole repository.** Transport and
shadow adapters are data/contract boundaries. The V2 runtime and legacy modules
still combine control, safety and transport-facing calls by design.

Required migration: keep transport adapters domain-free and route any future
V3 execution only through the execution boundary.

### Persistence

**PASS for V3 boundary; WARNING for production state.** V3 persistence contracts
use candidate/evidence semantics. V2 still owns active session, manual, OFF,
pause and recovery state surfaces.

Required migration: approve one state ownership map and recovery protocol before
any runtime cutover.

### Diagnostics

**PASS for pure V3 diagnostics; WARNING for legacy consumers.** The V3
diagnostics contract has no side effects. Legacy runtime logging and journal
paths remain active outside that boundary.

Required migration: mirror and reconcile event provenance before retiring legacy
writers.

## 3. Ownership map

| Authority | Current owner | Target/candidate | R2 status |
|---|---|---|---|
| Telemetry | V3 staged arbitrator over V2/HA/ESP sources | V3 | WARNING: staged, not control authority |
| Configuration | V3 canonical model plus V2 effective values | V3 | BLOCKED: source drift |
| Domain decisions | V2 live; V3 shadow | V3 | WARNING: no live transfer |
| Safety decisions | V2 runtime safety plus edge protections | one logical V3 model, V2/edge physical protections retained | BLOCKED |
| Execution | V2 transaction/runtime | V3 boundary | BLOCKED: dispatcher is shadow-only |
| Lease | ESPHome/edge dead-man with V2 renewal contract | separate verified lease authority | BLOCKED: exact contract evidence pending |
| Physical output | V2 physical layer; edge dead-man final protection | V3 only after staged gate | PASS for current ownership; migration BLOCKED |
| Diagnostics | V3 contracts mirrored with legacy consumers | V3 | WARNING |
| Persistence | V3 candidate/evidence boundary; V2 active stores | V3 boundary | WARNING |

There is no approved dual active owner for decision or execution. Current
ownership remains singular at the V2/edge boundary for physical behavior.

## 4. Actuator graph

The read-only graph in `application/actuator_reachability.py` and the existing
reachability map cover:

- `OUTPUT_ON`: V2 runtime, V2 startup/Mix, manual start/resume;
- `OUTPUT_OFF`: watchdog, manual stop, runtime containment, SafeOutput,
  lifecycle/recovery and managed adoption paths;
- `SET_VOLTAGE` / `SET_CURRENT`: V2 runtime, startup/recovery, manual/diagnostic
  and physical test/control paths;
- `STOP`, emergency stop and containment request paths.

**Status: BLOCKED.** The compatibility inventory is complete enough to expose
known paths, but production calls remain in `runtime/v2_runtime.py`,
`runtime_safety*.py`, `safe_output.py`, `manual_mode.py`, `v2_startup.py`,
`v2_mix_mode.py`, `runtime/v2_lifecycle.py`, adoption modules and related
physical-control modules. They do not all enter the V3 `ExecutionDispatcher`.

Required migration: prove every production writer through an approved V2
compatibility adapter first; only then stage a V3 execution bridge. No bypass
may be removed by this audit.

Deprecated candidates include diagnostic/probe and legacy direct paths, but
their retirement requires call-site proof and physical parity, not inventory
labels alone.

## 5. Configuration authority

**Status: BLOCKED.** `ConfigurationAuthority` provides typed owner/source/
default/validator contracts, and the unresolved registry prevents silent
precedence. It is not yet the sole effective production source.

Observed duplicate/conflicting sources include:

- YAML under `config/charge`, `config/safety`, `config/physical` and `config/runtime`;
- Python constants in `config.py`, `charge_logic.py`, `runtime/v2_runtime.py`,
  `runtime/charge/profiles` and safety modules;
- environment values and `.env`-derived runtime settings;
- persisted session/manual/OFF/pause/recovery values;
- embedded timers and thresholds in V2/physical modules.

Known unresolved decisions remain: EFB Mix 20/24 h, watchdog 180/300 s,
readback 5/10/15 s and operation-specific windows, lease renewal source and
interval, temperature policy, transport priority, FLOODED recipe and Custom
schema, Delta/hold unit semantics and OVP/OCP margin contexts.

Required migration: create provenance-backed parity vectors, resolve each value
through an approved decision, then switch authority in a separate staged change.

## 6. Safety ownership

**Status: BLOCKED.** Detection, decision and execution are conceptually
separated in the V3 contract, but existing production writers remain:

| Layer | Locations | R2 result |
|---|---|---|
| Detection | `runtime_safety.py`, `runtime_safety_v2.py`, `runtime_safety_strict.py`, watchdogs, lease and telemetry paths | WARNING: multiple detectors |
| Decision | V2 runtime safety, manual runtime, SafeOutput and edge lease paths | BLOCKED: multiple active decision/request paths |
| Execution | `SafeOutputCoordinator`, HA client wrappers and ESPHome/edge dead-man | PASS for fail-closed intent; not unified under V3 |

Direct or wrapped physical OFF/STOP actions remain reachable through
`_ensure_output_off`, `hass.turn_off`, manual containment, lease expiry and
SafeOutput. This is necessary current protection, not evidence of a single V3
safety owner.

Required migration: establish one audited decision coordinator while preserving
independent edge dead-man authority; prove OFF/readback/lease timing and
rollback on the exact target contract and bench before redirecting writers.

## 7. Runtime lifecycle

**Status: BLOCKED.**

- `bot.py` is the production entrypoint and performs top-level composition;
- `runtime/v2_runtime.py` constructs Telegram runtime and `HassClient` globals
  at import, and contains task/watchdog/lifecycle paths;
- `bot.py` creates background authority work from `main()`;
- `bot_legacy.py` remains rollback-only;
- manual/runtime/adoption modules create or own background tasks;
- V3 `runtime_composition.py` has explicit injected shadow lifecycle, but this
  does not remove V2 lifecycle ownership.

Required migration: build an import/startup inventory with restart and
cancellation evidence, then move V2 construction behind a separately approved
composition root. This cannot be done in a read-only audit.

## 8. Blocker register

| ID | Location | Severity | Why Stage 1 is blocked | Required migration |
|---|---|---|---|---|
| R2-B3 | V2 runtime, safety, manual, startup and physical-control call sites | BLOCKED | V3 cannot safely own decisions while physical paths bypass its boundary | exhaustive adapter reachability proof and parity |
| R2-B4 | YAML/Python/env/persisted/runtime defaults | BLOCKED | V3 decisions cannot reproduce one effective configuration | resolve provenance conflicts and stage authority |
| R2-B5 | runtime safety, SafeOutput, watchdog, lease, manual containment | BLOCKED | redirecting one writer can suppress or duplicate protection | single decision contract plus exact edge/bench evidence |
| R2-B6 | `runtime/v2_runtime.py`, `bot.py`, lifecycle/task modules | BLOCKED | import/startup side effects prevent clean dual lifecycle ownership | audited composition/lifecycle migration |
| R2-B2 | legacy domain/UI compatibility adapters | WARNING | V3 is not fully independent, though explicit seams now exist | complete domain/query-port extraction |

## 9. Stage decision

| Stage | R2 result | Evidence |
|---|---|---|
| Stage 0 — V2 current / V3 shadow | **PASS** | current ownership preserved; contracts and shadow tests remain non-actuating |
| Stage 1 — V3 decision / V2 execution | **BLOCKED** | R2-B2, R2-B3, R2-B4, R2-B5, R2-B6 and unresolved parity remain |
| Stage 2 — V3 execution / V2 fallback | **BLOCKED** | actuator bypass, rollback/readback and physical bench evidence incomplete |
| Stage 3 — full ownership | **BLOCKED** | all prior gates plus exact lease/ESPHome and physical validation required |

## 10. Audit conclusion

WORKSTREAM 2.1 and 2.2 improved observability and made transitional seams
explicit. They did not change the current safety posture or authorize a
cutover. **Stage 0 remains PASS; Architecture PASS and Stage 1 remain BLOCKED.**

No runtime, ownership, START, ACTIVE, HA, ESPHome, lease or physical behavior
was changed by this audit.
