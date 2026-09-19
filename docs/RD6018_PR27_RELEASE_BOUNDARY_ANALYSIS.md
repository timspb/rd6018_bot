# RD6018 PR #27 Release Boundary Analysis

Status: `BLOCKED`

Decision: **B — PR #27 contains accumulated migration layers that must be
split or explicitly accepted as a full migration release.**

No code, merge, deployment, or hardware action was performed.

## Scope facts

- Base: `ef2b4806a16723eaff67451667d0a2c73fca8fc4`
- PR HEAD: `c4baca2daef0b13baf8aa4a330c1cadd92856988`
- 272 commits / 626 files
- CI for HEAD: green on Python 3.10, 3.11, and 3.12

The change set is materially larger than a WS113B boundary patch.

## Hardware-affecting path inventory

| Path | Classification | Finding |
|---|---|---|
| `manual_mode.py` start -> `HassClient.safe_enable_output()` -> HA/RD | `BLOCKED_FOR_WS113B_SCOPE` | Direct physical start remains in the legacy manual manager; it is not an `ExecutionIntent`-only path. Requires explicit ownership decision. |
| `manual_mode.py` stop/error -> `HassClient.turn_off()` -> HA/RD | `BLOCKED_FOR_WS113B_SCOPE` | Three direct OFF paths remain. They may be safety/cleanup paths, but they bypass the new `ManualExecutionBoundary` contract. |
| `manual_mode.py` MAIN -> `ManualPhaseLifecycle` -> `ExecutionIntent` -> `ManualExecutionBoundary` -> injected V2 owner -> HA/RD | `ALLOWED_WITH_GUARD` | This is the intended WS113B MAIN-to-MIX setpoint path, provided the injected owner remains the sole V2 physical owner. |
| `runtime/v2_runtime.py` V2 controller -> `HassClient` -> HA/RD | `ALLOWED` | Existing V2 physical owner; must remain the only production owner during this migration. |
| `runtime/physical/connectors/ha_esp.py` -> HA service API -> RD | `BLOCKED_UNTIL_EXPLICIT_WIRING_REVIEW` | Physical connector with setpoint/output methods. It is an execution adapter, not a passive reader. |
| `runtime/physical/connectors/esp_direct.py` -> ESPHome API -> RD | `BLOCKED_UNTIL_EXPLICIT_WIRING_REVIEW` | Independent physical connector with write methods. It creates a second execution surface unless proven non-production. |
| `runtime/output/bridge/PhysicalBridgeExecutor` -> injected transport -> hardware | `BLOCKED_UNTIL_EXPLICIT_WIRING_REVIEW` | Real executor with gate, lease, command application, and readback verification. Not merely a state model. |
| `runtime/output/executor/*` -> command plan / dry-run / executor contracts | `ALLOWED_FOR_SIMULATION_ONLY` | Contract and simulation layer; must not be reachable from production control without a separately approved owner bridge. |

## `runtime/physical/**` analysis

This tree is not only an adapter package. It contains:

- HA and ESPHome connectors with write operations;
- command models and target validation;
- physical lease models/providers;
- hardware safety envelopes;
- verification services and readback comparators.

Therefore it is a complete physical execution subsystem. It is not proven to
be a second active owner in the current `bot.py` import graph, but it is a
second executable surface and cannot be accepted as harmless infrastructure
without an explicit composition/wiring audit.

## `runtime/output/**` analysis

This tree contains both state/intent models and an execution surface.
`PhysicalBridgeExecutor` calls injected transport methods such as `apply`,
`disable_output`, and readback operations, and it enforces its own gate and
lease. It must be classified as execution infrastructure, not as a passive
state model.

## `manual_mode.py` analysis

Observed calls:

- `safe_enable_output()` during manual start — physical execution;
- `turn_off()` in normal stop — physical execution;
- `turn_off()` in stop confirmation — physical execution;
- `turn_off()` on runtime exception — physical containment;
- `get_all_live()` — observation;
- `execution_boundary.apply(...)` for MAIN-to-MIX — approved boundary path.

There are no direct `set_voltage()` or `set_current()` calls in
`manual_mode.py`; the MAIN-to-MIX target application is delegated. However,
the direct start/OFF paths mean the file is not purely an intent source.

## Migration decision

The current evidence supports **B**, not A:

1. Extract a narrow WS113B release containing the manual lifecycle,
   execution boundary, identity/audit contracts, and focused tests/docs; or
2. Treat PR #27 as a full migration release and perform a separate review of
   all runtime, physical, lease, UI, config, and rollback changes.

Option C is not yet proven for the entire PR, but the physical execution
surfaces and direct manual stop/start paths are architecture blockers for a
narrow WS113B release and require redesign or explicit boundary acceptance.

## Required before merge

- Decide ownership for `safe_enable_output()` and direct manual `turn_off()`;
- prove `runtime/physical/**` and `runtime/output/**` are not an additional
  production owner, or remove/split them;
- preserve V2 rollback/runtime provenance;
- separate physical/bench deployment changes from the WS113B release;
- resolve `git diff --check` failures in the accumulated diff;
- rerun the full CI matrix on the final reviewed scope.

Final status: `BLOCKED`
