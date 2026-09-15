# RD6018 Ownership Manifest

Status: Phase 1, characterization only.

This manifest freezes the current ownership boundaries before further V3
migration. It is not an authorization to move actuator calls or change runtime
behavior.

## Ownership

| Domain | Current owner | Boundary | Phase 1 rule |
|---|---|---|---|
| Telegram intent/UI | `v2_bot_ui.py`, `operator_hmi.py`, `telegram/*` | `OperatorIntent` / route adapters | UI must not call physical APIs |
| V3 preflight and plan | `application/*` | `StartPreflightService`, `ApprovedStartPlan` | read-only only |
| V3 trace/activation | `application/*` | execution contract and activation policy | no ACTIVE by default |
| START execution | `v2_bootstrap.py` composition -> V2 adapters | `V2StartTransactionAdapter` | V2 remains owner |
| Automatic FSM | `ChargeControllerV2` / `DiagnosticProductionChargeControllerV2` | `charge_controller_v2.py`, `diagnostic_controller.py` | no second FSM |
| Manual session | `ProductionManualSessionManager` -> `ManualSessionManager` | `manual_mode.py`, `manual_runtime_v2.py` | session lifecycle remains V2 |
| Safety decision | `runtime_safety.py`, `runtime_safety_v2.py`, `runtime_safety_strict.py` | safety wrappers and guardrails | fail-closed behavior unchanged |
| Output transaction | `SafeOutputCoordinator` and composed Hass safety surface | `safe_output.py`, `hass_api.py` | no UI/direct V3 writes |
| Physical execution | V2 runtime / HA and edge adapters | `hass_api.py`, `runtime/v2_runtime.py`, ESPHome lease | no ownership migration in Phase 1 |
| Telemetry | HA/direct readers as currently composed | `hass_api.py`, telemetry modules | authority migration is separate work |
| Lease/dead-man | `EdgeSafetyLease` plus ESPHome local contract | `edge_safety_lease.py`, `esphome/packages/*` | lease TTL/semantics unchanged |

## Static invariants

1. `application`, `runtime.application`, `runtime.ui`, and `telegram` do not
   import physical connectors or instantiate actuator objects.
2. Telegram/UI code does not call `turn_on`, `turn_off`, `set_voltage`,
   `set_current`, `controller.start`, or `controller.stop` directly.
3. The production V3 route is composed by `v2_bootstrap.py`; V2 remains the
   execution owner behind the adapter.
4. Legacy direct call sites remain explicitly inventoried until a reviewed
   migration removes them.

## Explicit transitional surfaces

The preserved `runtime/v2_runtime.py`, legacy UI modules, diagnostic probes,
manual runtime, and safety wrappers still contain actuator-capable call sites.
They are not silently reclassified as V3 ownership. Their removal requires a
separate behavior-parity and bench-gated change.
