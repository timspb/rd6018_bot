# RD6018 architecture guardrails (Phase 6.1)

Статус: tooling/tests only. Эти проверки защищают новые границы и не меняют
runtime behavior.

## Enforced boundaries

### Domain isolation

`runtime/charge` may depend on standard-library and domain modules only. Imports
of Telegram, HA, ESPHome, persistence stores, physical adapters, controllers,
transport clients and output executors are forbidden.

### UI isolation

`application/operator_*` is presentation/application-facing code. It may create
operator intents and render snapshots, but must not import or mutate FSM,
ChargeController, physical adapters, HA/ESP clients or output executors.

### Infrastructure isolation

`runtime/physical` and transport adapters may translate transport calls and
readbacks. They must not import charge programs, FSM transitions, UI modules or
Telegram handlers. Telemetry transport is data acquisition, not domain logic.

### Composition-root purity

The composition contract may create dependencies and wire ports. It must not
contain recipes, thresholds, transition algorithms, safety decisions, Telegram
handlers or physical calls. Transitional `v2_bootstrap.py` is checked for the
same absence of phase algorithms and actuator calls while it remains in place.

## Bootstrap inventory

| Path | Classification | Allowed role |
|---|---|---|
| `bot.py` | production entrypoint | one startup handoff; transitional installer composition |
| `v2_bootstrap.py` | transitional composition | connect current V2 owners and dry-run ports |
| `runtime/v2_runtime.py` | legacy V2 runtime surface | current compatibility/runtime owner |
| `bot_legacy.py` | rollback-only | explicitly selected emergency compatibility entrypoint |
| `v2_startup.py` / recovery | startup/transaction compatibility | existing V2 owner; not a second production root |

The checks allow rollback/compatibility entrypoints but require exactly one
production entrypoint marker (`bot.py`). They also reject a new `__main__` root
under `application` or `runtime/charge`.

## Hidden-global and duplicate-root policy

- no new module-global controller, transport, FSM or persistence owner in the
  contract/domain packages;
- no second production `asyncio.run(main())` entrypoint;
- rollback entrypoints must remain explicitly classified as rollback-only;
- adding an installer does not create a new composition root.

The checks are static AST/import checks. They do not prove runtime reachability
or physical safety and therefore do not authorize START/ACTIVE.

## Failure policy

Any newly added boundary violation fails the test suite. Existing legacy
composition is inventoried and constrained without being silently rewritten.
