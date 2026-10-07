# RD6018 documentation authority

This index defines which documents describe the **current executable system**
and which files are retained only as migration/evidence history.

## Current authority

Use these first:

- `V3_PROJECT_RUNBOOK.md` — chronological project authority and current boundary.
- `V3_MODULAR_ARCHITECTURE.md` — required module/layer rules.
- `V3_UI_MODULAR_ARCHITECTURE.md` — UI/application/transport boundary.
- `V3_LEGACY_ERADICATION_LEDGER.md` — removal ledger and proof status.
- `RD6018_COMPOSITION_ROOT_MODEL.md` — current single-root composition contract.
- `DEPLOYMENT.md` — deployment and rollback procedure.
- `RD6018_FAILSAFE.md` — physical/edge fail-safe rules.
- `V3_START_PRODUCTION_ROUTE_WIRING.md` and `V3_START_BENCH_READINESS_REVIEW.md` — current START path.
- `V3_BENCH_VALIDATION_PROTOCOL.md` and physical evidence files — bench safety/evidence.

When a current-authority document conflicts with a historical phase document,
the current-authority document wins.

## Historical evidence

Files named `V3_PHASE*`, older `RD6018_*_MODEL.md` migration models,
`*_PARITY*`, `*_SHADOW*`, handoff prompts and `docs/assistant/*` are
retained to explain how the current architecture was reached. They are not
permission to reintroduce deleted compatibility layers or retired authority.

Historical documents may mention modules that no longer exist. Treat those
mentions as evidence only.

## Removed compatibility surfaces

The following names are intentionally absent from executable code:

- `bot_legacy.py`
- `runtime/v2_runtime.py`
- `v2_startup.py`
- `application/v2_start_runner_adapter.py`
- `application/legacy_actuator_boundary.py`
- `v1_ui_compat.py`
- `application/v2_identity_bridge.py`
- `application/operator_snapshot_shadow.py`
- `runtime/ui/legacy_shadow/*`
- legacy START feedback bridge modules

Do not recreate a forwarding shim for any removed name. Move callers to the
current owner instead.

## Production naming status

Production-reachable filenames no longer use the historical `v2_*`/`*_v2`
module namespace. Names such as `*_readback_v2` that remain in code are external
RD6018/ESPHome telemetry schema identifiers, not alternate runtime ownership.
Historical comparison/evidence modules may still use V2/V3 terminology and are
not imported by the production root.

## Evidence documents

Dated physical-validation files are immutable operational evidence except for
clarifying factual errors. They do not define architecture on their own.

## Update rule

Every merged architectural change must update this index only if authority
changes, and must update the runbook/ledger in the same PR. New migration
documents must declare `current`, `historical`, or `evidence` status near
the top.
