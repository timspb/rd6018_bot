# RD6018 Final Architecture Audit R3

Audit mode: read-only after WORKSTREAM 3. No runtime behavior, live ownership,
V2 physical execution, START/ACTIVE, HA/ESP control or lease ownership changed.

## Executive result

**Stage 0: PASS — preserved.**

WORKSTREAM 3 improved adapter isolation and produced canonical actuator,
configuration and safety/lifecycle inventories. It did not and could not close
the remaining production migration blockers under the stated restrictions.

**Architecture PASS: NOT GRANTED. Stage 1: BLOCKED.**

## R3 status matrix

| Area | R2 | R3 | Result |
|---|---|---|---|
| B2 legacy domain boundary | WARNING | IMPROVED | named adapter is the only application seam; full domain extraction pending |
| B3 actuator ownership | BLOCKED | MAPPED / BLOCKED | canonical map complete as inventory; V2 bypasses remain |
| B4 configuration authority | BLOCKED | INVENTORIED / BLOCKED | provenance/status registry added; conflicts remain unresolved |
| B5 safety ownership | BLOCKED | EXPLICIT / BLOCKED | detection/decision/execution map added; physical writers remain |
| B6 lifecycle separation | BLOCKED | INVENTORIED / BLOCKED | V3 contract layer isolated; V2 import-time lifecycle remains |

## Module isolation

- UI uses an explicit legacy read adapter, but that adapter still reads V2
  presentation/infrastructure sources: `WARNING`.
- V3-facing application modules do not directly import `runtime.charge`; the
  only application adapter that imports it is
  `application/legacy_domain_adapter.py`: `IMPROVED`, not full extraction.
- Pure V3 contract modules remain free of HA/ESP/physical implementations:
  `PASS` for the contract layer.
- Persistence and diagnostics contracts remain side-effect-free, while V2
  active state and legacy logging remain separate: `WARNING` for whole graph.

## Ownership

The current authority matrix is unchanged:

- telemetry: V3 staged view over existing sources;
- configuration: V3 candidate model, V2 effective values;
- decision/domain: V2 live, V3 shadow;
- safety: V2 runtime plus SafeOutput and edge dead-man;
- execution/physical: V2 and edge protections;
- lease: ESPHome/edge contract with V2 renewal path.

No implicit transfer or dual active decision/execution owner was introduced.

## Actuator graph

`application/actuator_ownership_map.py` now provides the canonical static map,
covering ON/OFF, voltage/current, START/STOP, emergency and containment paths,
including V2 runtime, SafeOutput, runtime safety, manual/diagnostic, startup,
recovery, edge lease and ESP Direct adapter locations.

Result: **MAPPED but BLOCKED for migration**. Existing production calls still
reach V2 physical boundaries without entering the V3 dispatcher. The inventory
does not redirect or execute any path.

## Configuration authority

`application/configuration_registry.py` adds typed/provenance/status records on
top of the existing authority and unresolved-decision registry. This makes the
drift visible but does not select conflicting values. Remaining conflicts include
Mix budget, watchdog, readback windows, lease renewal, temperature policy,
transport priority, FLOODED/Custom schema and Delta/hold semantics.

Result: **inventory complete enough for audit; effective authority BLOCKED**.

## Safety ownership

`application/safety_ownership_map.py` separates detection, canonical logical
decision owner and existing physical execution boundary. Tests verify one logical
decision owner and detect multiple current execution writers. No safety writer
was removed, wrapped, or redirected.

Result: **model explicit; production consolidation BLOCKED**.

## Lifecycle

The lifecycle inventory confirms:

- `bot.py` remains the V2 production composition root;
- `runtime/v2_runtime.py` retains import-time Telegram/HA globals and workers;
- `bot_legacy.py` remains rollback-only;
- V3 `ApplicationComposition` remains shadow/contract-only.

Result: **V3 contract isolation PASS; whole-runtime lifecycle separation
BLOCKED**.

## Stage decision

| Stage | R3 result | Reason |
|---|---|---|
| Stage 0 — V2 current / V3 shadow | **PASS** | current owner and physical behavior preserved |
| Stage 1 — V3 decision / V2 execution | **BLOCKED** | unresolved config, safety consolidation, lifecycle and adapter gaps |
| Stage 2 — V3 execution / V2 fallback | **BLOCKED** | actuator bypass and verification/bench evidence incomplete |
| Stage 3 — full ownership | **BLOCKED** | requires all earlier gates plus exact lease/ESPHome validation |

## Verification

- Workstream 3 tests: 5 OK;
- Workstream 1 tests: 5 OK;
- Workstream 2 tests: 8 OK;
- Workstream 2.2 tests: 6 OK;
- application compileall: OK;
- `git diff --check`: OK.

## Conclusion

R3 confirms that Workstream 3 improved separation and observability without
changing safety behavior. It does not justify Architecture PASS or Stage 1.
The next permitted work is migration preparation with explicit parity and
physical/ESPHome bench gates, not live ownership transfer.
