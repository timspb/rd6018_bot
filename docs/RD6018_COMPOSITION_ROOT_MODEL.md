# RD6018 composition root model

Status: **current modular production composition**.

## Current production root

`bot.py` is the only production entrypoint. It composes the canonical
`runtime.production_runtime` substrate through `ProductionComposition`.
The retired compatibility facades are absent: there is no `bot_legacy.py`,
no `runtime.v2_runtime`, no top-level `v2_startup.py`, no
`application.v2_start_runner_adapter`, and no legacy actuator inventory facade.

`production_bootstrap.py` is a production composition installer module. It is not
a second production root and contains no charge-state machine or direct physical
writes.

## ApplicationComposition contract

There is one authoritative `ApplicationComposition` shape:

```text
ApplicationComposition
├── domain
├── application
├── infrastructure
├── ui
└── persistence
```

The composition root creates/connects owners and adapters. It must not own
charge decisions, safety policy, Telegram callback semantics, physical I/O,
persistence policy, or a second bootstrap.

## Single-root invariant

A running process has one startup handoff: `bot.main() -> ProductionComposition.run()`.
The runtime lifecycle is delegated to the composed canonical runtime only.
Any second bootstrap, module-alias facade, or compatibility entrypoint is a
regression.

## Naming and external compatibility boundaries

Production-reachable module filenames and internal owner types use neutral current
names. Historical-looking names may remain only in persisted state, Telegram
callback-data, deployed ESPHome/entity schemas or explicit historical evidence;
those are protocol/state boundaries and require explicit migration rather than
textual renaming. New production modules must not reintroduce `v2_*`, legacy,
shadow or compatibility ownership surfaces.

## Guardrail

Static architecture tests require retired facades to remain absent and prevent
reintroduction of direct physical calls into the bootstrap/composition layer.
