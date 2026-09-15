# RD6018 V3 Boundary Cleanup & Decoupling — WORKSTREAM 2

Status: **partial cleanup complete; Stage 0 behavior preserved; architecture
PASS not yet reached**.

The work was restricted to explicit contracts, compatibility adapters,
inventories and static tests. No ownership transfer, Stage 1 enablement, V2
execution change, HA/ESP write, lease change or physical command was performed.

## 1. Blocker disposition

| Original blocker | Result | Evidence/change | Residual risk |
|---|---|---|---|
| UI / infrastructure coupling | `IMPROVED` | `application/operator_snapshot_provider.py` now depends on explicit read-only `LegacyUIReadAdapter`; direct HMI/telemetry/journal/diagnostics imports were removed | Adapter still wraps legacy V2 reads and must remain outside pure UI/domain |
| Legacy domain imports | `OPEN` | inventory confirms `application/charge_orchestration.py` and `shadow_composition.py` still use `runtime.charge` | V3 domain is not fully independent of legacy package |
| Actuator bypasses | `OPEN / INVENTORIED` | `legacy_actuator_boundary.py` registers every known V2 operation as non-dispatching compatibility path | Production callers remain outside V3 `ExecutionDispatcher`; no path was silently removed |
| Configuration drift | `OPEN / EXPLICIT` | `configuration_decision_registry.py` records unresolved watchdog, readback, transport, lease, profile and Mix decisions without selecting values | `ConfigurationAuthority` is not yet sole effective production source |
| Safety owner consolidation | `OPEN / CONTRACTED` | `safety_boundary.py` separates detection → decision → containment request as data-only contracts | Existing V2/edge safety owners remain active and cannot be consolidated without runtime parity/bench work |
| Import-time V2 coupling | `OPEN / PRESERVED` | no V2 import/startup behavior changed | `runtime/v2_runtime.py` still constructs Telegram/HA globals at import and owns legacy workers |

## 2. New boundaries

### UI compatibility boundary

```text
UI provider
    |
    v
LegacyUIReadAdapter (read-only)
    |
    v
V2 HMI / telemetry / journal source
```

The adapter is the only compatibility seam used by the refactored provider.
It cannot issue start/stop/output commands; operator commands remain
`OperatorIntent` values.

### Safety decision boundary

```text
SafetySignal
    |
    v
SafetyDecision
    |
    v
ContainmentRequest
    |
    v
existing V2/edge execution owner
```

The new layer is data-only and not connected to production safety writers.

### Actuator compatibility inventory

All known `OUTPUT_ON`, `OUTPUT_OFF`, `SET_VOLTAGE` and `SET_CURRENT` legacy
paths are represented by `LegacyActuatorCompatibilityPath`. Every entry has an
owner and boundary classification and `dispatch_enabled=False`. This is an
inventory/guardrail, not a replacement of V2 execution.

### Configuration unresolved-decision registry

Conflicting values are now explicit registry entries rather than implicit
precedence. The registry intentionally does not choose between:

- EFB Mix 20 h / 24 h;
- watchdog 180 s / 300 s;
- 5 s / 10 s / 15 s readback windows;
- transport default/priority variants;
- lease renewal source/interval variants;
- FLOODED and Custom profile schemas;
- staged temperature policy variants.

## 3. Test coverage

- UI provider no longer imports legacy infrastructure modules directly;
- all known actuator operations are inventoried and non-dispatching;
- safety data flow is detection → decision → request;
- configuration conflicts are present and remain `UNRESOLVED`;
- original Workstream 1 blockers remain visible in the audit;
- existing UI regression suite remains green.

## 4. Residual blockers before architecture PASS

1. Extract V3 domain behind a proper domain port/adapter and remove direct
   `runtime.charge` imports from V3 composition.
2. Perform a complete actuator reachability migration while retaining V2 as
   owner; prove every production writer enters the approved compatibility
   boundary.
3. Resolve configuration decisions through explicit parity evidence, then
   make the canonical model authoritative only in a separately approved step.
4. Introduce one runtime safety decision owner without suppressing independent
   ESPHome dead-man protection or changing existing fail-safe behavior.
5. Move V2 module construction behind an explicit composition lifecycle only
   after a dedicated startup/import regression plan.

## 5. Acceptance result

`STAGE0_BEHAVIOR_PRESERVED` — yes.

`ARCHITECTURE_PASS` — no; blockers B2, B3, B4, B5 and B6 remain explicitly
open. This is intentional: changing them now would violate the Workstream 2
prohibition on V2 execution/physical behavior and ownership transfer.

## Restrictions confirmed

V2 runtime, START, ACTIVE, HA, ESP, lease ownership, physical ownership,
configuration values and production execution were not changed.
