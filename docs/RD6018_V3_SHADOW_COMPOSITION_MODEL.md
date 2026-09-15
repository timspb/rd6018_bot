# RD6018 V3 shadow composition — Phase 8.6

## Graph

`application.shadow_composition.ApplicationComposition.shadow()` assembles the
V3-only graph:

```text
UI adapter
    |
    v
ChargeApplicationService -> pure runtime/Domain
    |
    v
ExecutionDispatcher -> shadow transport adapters

ConfigurationAuthority, DiagnosticsDomain and PersistenceProvider
are explicit cross-cutting dependencies.
TelemetryAuthority is injected separately and has no control methods.
```

Components:

- `OperatorUIAdapter`;
- `ChargeApplicationService` and pure `runtime.charge` domain objects;
- `ConfigurationModel` / `ConfigurationAuthority`;
- HA and ESP Direct read-only telemetry adapters plus arbitrator;
- `ExecutionDispatcher`;
- HA/ESP-shaped shadow execution adapters;
- in-memory persistence provider;
- `DiagnosticsDomain`.

## Injection rules

Readers are passed into the composition as callables. If omitted, empty
in-memory readers are used; no network client is constructed. Persistence is
always `InMemoryPersistenceProvider` in this phase. Configuration reads only
the explicitly mapped tracked YAML files when a `config_root` is supplied.

## Forbidden behavior

The shadow composition does not import or start production Telegram, `bot.py`,
HA clients, ESP clients, V2 runtime bootstrap, or physical adapters. It does
not write files, SQLite, HA, ESPHome or RD6018 and does not enable START or
ACTIVE.

## Validation scope

Tests cover composition creation, dependency injection, UI command flow,
telemetry selection, domain decision, diagnostic correlation, persistence
candidate creation and no-side-effect import/call boundaries.
