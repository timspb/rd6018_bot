# D123 Sprint 55C evidence — 2026-10-21

## Scope and start

Source-only continuation on `codex/d118-start-lease-repair-20261019`, starting
from exact clean HEAD `eb1e37b9cf61bc127a1cb0d79734683be6b7779b`. No node104,
ESP, HA, firmware, services, deployment, GitHub, or physical Output interaction
was performed. No dependencies, recipes, safety thresholds, lease behavior,
Manual behavior, OVP/OCP, or ESP priority were changed.

## Before and after host graph

Before:

```text
ManagedChargeController
└── ProductionChargeController
    └── AutoStrategyProductionChargeController

DiagnosticProductionChargeController = ProductionChargeController
runtime.production_runtime -> ProductionChargeController(...)
production_bootstrap -> isinstance(..., ProductionChargeController)
```

`ProductionChargeController` declared no methods; it selected production
extension initialization and legacy restore defaults through three class
attributes. `AutoStrategyProductionChargeController` was an empty subclass.
Diagnostic was a direct alias.

After:

```text
ManagedChargeController(host_configuration=PRODUCTION_CHARGE_HOST_CONFIGURATION)
runtime.production_runtime -> create_production_charge_host(...) -> exactly ManagedChargeController
production_bootstrap -> configure_production_charge_host(existing canonical instance)
```

There is exactly one mutable FSM/session state host and it is exactly the
canonical `ManagedChargeController` class. No production controller subclass,
facade, or mixin remains. `auto_strategy.py` and `diagnostic_controller.py` have
no controller class or active production import. Internal tests now use the
canonical production host factory rather than a test-only subclass.

## Explicit host configuration

`runtime.charge.host_configuration.ManagedChargeHostConfiguration` is a frozen
dataclass with only three policy values:

- `production_extensions_enabled: bool`
- `restore_trace_default_intent: str`
- `restore_trace_default_condition: str`

`PRODUCTION_CHARGE_HOST_CONFIGURATION` selects `True`, `normal`, and `unknown`, preserving the exact production migration defaults without importing `pb_domain` into the pure runtime/charge layer. Standalone `ManagedChargeController` construction gets a fresh immutable default policy: extensions disabled, `recovery`, `unknown`, matching its previous instance defaults. This value object owns no FSM/session or mutable runtime state.

`ManagedChargeController.__init__` consults the instance configuration to run
`initialize_production_session_state` and diagnostic initialization only for a
production host. Restore consults the same instance configuration to preserve
ordinary session -> MAIN Guard reconstruction -> production extensions -> MIX
active authority ordering. `runtime.charge.session.restore_trace_identity`
uses configured intent/condition defaults for deterministic legacy migrations.

The runtime imports and calls the pure production host factory once. Bootstrap
requires `type(host) is ManagedChargeController`, configures that same object in
place, and does not replace a host already configured with the canonical
production value. A wrongly configured canonical instance receives production
configuration and production-only initialization without replacing its
identity. Non-canonical objects are replaced with one factory-created canonical
host, consistent with the existing bootstrap boundary.

## Architecture gates and tests

`tests/test_d123_sprint55c_architecture.py` requires no former production
controller classes or active `ManagedChargeController` subclasses, one runtime
factory construction, frozen/state-free configuration, same-object bootstrap
configuration, ordered Guard/extension restore, and no duplicate persistence or
physical writer. `test_production_entrypoint`, Sprint 55B architecture gates,
recipe-policy gates, and extension-ownership gates were migrated to the new
canonical class and factory.

Focused Python 3.12 batch covering production entrypoint/bootstrap, production
controller, cooling, done/storage restore, Guard binding, MIX timeout and
preemption, diagnostics, Sprint 55B/55C architecture, recipe and extension
ownership, final SAFE_WAIT, guardrails, AUTO callers, recovery/MIX migration,
notification isolation, and recovery continuation: **141 PASS**. A first run
with system Python lacked installed repository dependencies; no dependencies
were installed. The repository's existing Python 3.12 environment was used for
the passing focused run.

Outer canonical direct WSL Python 3.12 discovery after the final layering correction: **2,462 tests, 3 skipped, PASS**. The first outer run exposed one real architecture violation: `runtime/charge/host_configuration.py` imported `pb_domain`. The config was made domain-neutral by storing only string policy values; architecture/layering focused tests then passed **8/8**, and the repeated full suite passed. Full log: `/tmp/d123-s55c-canonical.log`. `python -m compileall -q .`: **PASS**. `git diff --check`: **PASS**.

## Status and remaining work

- **P4 class-shape objective: CLOSED.** Active production uses the canonical
  `ManagedChargeController` with explicit immutable non-inheritance
  configuration; neither `ProductionChargeController` nor
  `AutoStrategyProductionChargeController` class remains.
- **P2 remains open:** MAIN Guard admission and remaining canonical raw-session
  document/audit lifecycle ownership. Current fail-closed behavior and restore
  order were preserved.
- **P5 remains open:** release matrix and exact source gates, Python
  3.10/3.11/3.12 matrix, and separately supervised physical acceptance. No
  deployment or physical validation was performed.
