# V3 production boundary stabilization audit

## Current production composition

```text
bot.py
  |
  +-- bot_legacy composition / V2 controller and safety wrappers
  +-- application.OperatorSnapshotProvider
  |      |
  |      +-- runtime.ui presentation DTOs
  |      +-- runtime.diagnostics read-only evidence
  |      +-- runtime.journal formatting
  |
  +-- Telegram/dashboard adapters
         |
         +-- OperatorInterface read path
         +-- preserved callback execution paths
```

The V3 application layer is currently a compatibility boundary around the
preserved V2 runtime. It reads sanitized snapshots and routes already-migrated
STOP/PAUSE/RESUME/profile intents; START remains shadow/preflight only.

## Application contract audit

Current application contracts import these transport-independent DTOs:

- `runtime.ui.models.DiagnosticsView`;
- `runtime.ui.models.RuntimeUISnapshot` and related view models;
- `runtime.ui.commands.models` for command result/domain intent types;
- `runtime.diagnostics.DiagnosticAuthority` for read-only diagnostic state.

These are candidates for a future `application/contracts` package if the
application layer must become independent of the presentation/runtime package.
No relocation is performed in this stabilization step because it could alter
import identity and production behavior.

## Physical isolation result

The production import graph rooted at `bot.py` was checked statically. It does
not reach:

- `runtime.physical`;
- `runtime.output.executor`;
- `PhysicalExecutionGate`;
- `PhysicalBridgeExecutor`;
- `HAESPConnector`;
- `ESPDirectConnector`.

This is now enforced by
`tests/test_v3_production_physical_isolation.py`. Bench/physical modules remain
available only to explicitly selected tests and bench tooling.

## Evidence classification

The following documents are bench evidence, not production claims:

- `docs/V3_FIRST_PHYSICAL_DISABLE_EVIDENCE_2026-09-13.md` — verified-off
  bench action only; Output was already OFF and no charge was started.
- `docs/V3_FIRST_PHYSICAL_EXECUTION_EVIDENCE_2026-09-13.md` — two independent
  bench `DISABLE_OUTPUT` runs with readback; it explicitly does not prove an
  `ON -> OFF` transition or production migration.
- `docs/V3_OUTPUT_STATE_TRANSITION_EVIDENCE_2026-09-14.md` — controlled bench
  state transition evidence; it is not an authorization for automatic or
  production execution.

None of these files is treated as proof that V3 owns production actuator
execution. Production remains on the preserved V2 path.

## Remaining boundary work

1. Move shared DTOs to application-owned contracts without changing identity or
   behavior.
2. Keep START at preflight/trace until its execution owner and rollback/OFF
   semantics are separately approved.
3. Preserve the physical import isolation test while adding any future bench
   entrypoint.

