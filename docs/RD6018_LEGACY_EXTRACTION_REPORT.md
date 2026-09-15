# RD6018 Legacy Extraction & Ownership Cleanup — WORKSTREAM 2.1

Status: **boundary extraction and inventory complete; architecture PASS still
blocked**.

No ownership transfer, Stage 1 enablement, V2 execution change, HA/ESP write,
lease change or physical operation was performed.

## B2 — Legacy domain import extraction

### Found

- `application/charge_orchestration.py` and
  `application/shadow_composition.py` previously imported `runtime.charge`
  directly;
- `runtime.charge` is the preserved V2-compatible domain implementation;
- V3 shadow composition needs the domain registry/session objects but must not
  silently become a second V2 owner.

### New boundary

`application/legacy_domain_adapter.py` is now the explicit compatibility seam.
V3-facing application modules import the named adapter, while the adapter is
the only place that imports the legacy domain package. The adapter is data/
behavior compatibility only and does not own execution.

Migration status: `IMPROVED / ADAPTER_REQUIRED`. Full V3 domain replacement
remains a later migration because parity and ownership are not complete.

## B3 — Actuator bypass extraction

The existing [actuator reachability map](RD6018_ACTUATOR_REACHABILITY_MAP.md)
was used as the source inventory. All known Output ON/OFF, voltage/current,
controller start/stop, watchdog, manual and containment paths remain preserved.

`application/legacy_actuator_boundary.py` turns the inventory into explicit
non-dispatching compatibility records. Each record has caller, current owner,
operation and boundary; `dispatch_enabled=False` is mandatory.

Target graph remains:

```text
Domain -> ActuatorIntent -> ExecutionDispatcher -> Adapter -> Physical
```

Migration status: `INVENTORIED / OPEN`. Existing V2 writers are intentionally
not redirected in this workstream because that would change physical behavior.

## B4 — Configuration conflict normalization

`application/configuration_decision_registry.py` records parameter identity,
section, sources, candidates, owner and status. It contains explicit
`RESOLVED`, `UNRESOLVED` and `MIGRATION_REQUIRED` entries.

No conflict was resolved by assumption. The registry keeps unresolved:
watchdog values, readback windows, transport priority, lease renewal source,
Mix budget, FLOODED/Custom schema and staged temperature policy.

Migration status: `EXPLICIT REGISTRY / OPEN`. `ConfigurationAuthority` is not
yet the effective production source for all V2 values.

## B5 — Safety ownership consolidation

`application/safety_boundary.py` defines the data-only flow:

```text
SafetySignal -> SafetyDecision -> ContainmentRequest -> existing execution owner
```

All inventoried triggers use one logical `Safety Decision Authority` in the
new contract. No contract field or helper permits a physical write. Existing
V2 runtime safety, SafeOutput and ESPHome dead-man owners remain untouched.

Migration status: `CONTRACTED / OPEN`. Consolidating production writers needs
parity, rollback and exact edge/bench evidence.

## B6 — Import-time V2 runtime decoupling

`application/composition_lifecycle.py` defines an explicit injected lifecycle
contract whose construction has no startup side effects. Static tests reject
`asyncio.run` and direct `runtime.v2_runtime` imports from application modules.

The preserved V2 module still constructs Telegram/HA globals at import and
owns legacy workers. This was deliberately not changed because moving it is a
runtime migration with restart and rollback risk.

Migration status: `CONTRACTED / OPEN`. The production composition root remains
`bot.py`; V2 import-time construction is a documented compatibility debt.

## Tests and repeat audit

Added checks cover:

- forbidden direct V3 legacy-domain imports;
- actuator operation inventory and non-dispatching compatibility paths;
- configuration status completeness;
- one canonical safety decision owner in the new contract;
- no implicit application runtime start;
- UI regression through the explicit UI adapter.

Repeat Workstream 1 audit result: **Stage 0 behavior preserved; architecture
PASS not yet reached**. Remaining blockers are B3, B4, B5 and B6; B2 is now
behind an explicit adapter but is not fully migrated.

## Remaining risks

1. A compatibility adapter is not the same as domain extraction.
2. Inventory-only actuator records do not prove every production reachability
   path enters the future dispatcher.
3. Unresolved configuration values still prevent canonical effective runtime
   configuration.
4. Multiple existing safety writers must not be deduplicated without physical
   parity evidence.
5. V2 import-time side effects remain until a separately approved lifecycle
   migration.
