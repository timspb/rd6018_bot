# RD6018 Final Architecture Audit R4

Audit mode: controlled migration preparation. No live ownership transfer, V2
runtime modification, START/ACTIVE change, HA/ESP write, lease change or
physical command was performed.

## Executive result

The new `v3_core` is a standalone pure package with no V2, legacy runtime,
transport or physical imports. Its domain, safety, configuration, intent,
shadow execution and composition contracts pass static validation.

**Pure V3 core: PASS.**

**Production Architecture PASS: NOT GRANTED.**

Production V2 paths remain unchanged and therefore remain the current physical
and safety execution system. Removing them or replacing them requires exact
adapter/readback/rollback and ESPHome bench evidence outside this turn.

## R4 matrix

| Criterion | Result | Evidence |
|---|---|---|
| no V2 imports in V3 core | PASS | `tests/test_workstream4_v3_core.py` AST check |
| no legacy state/execution in V3 core | PASS | pure `v3_core` dependency graph |
| one V3 actuator boundary | PASS for shadow | `v3_core.execution.ExecutionDispatcher` |
| one V3 safety decision owner | PASS for pure core | `v3_core.safety.SafetyDomain` |
| one V3 configuration contract | PASS for schema | `v3_core.configuration.ConfigurationAuthority` |
| one production actuator path | BLOCKED | V2 physical writers remain active |
| one production safety owner | BLOCKED | V2/SafeOutput/edge protections remain |
| one production lifecycle owner | BLOCKED | `bot.py`/`runtime/v2_runtime.py` remain production |
| legacy physical path elimination | BLOCKED | physical parity and bench gate absent |

## Pure-core review

### Domain/Application/Decision

`v3_core.domain.ChargeDomain` consumes only V3 telemetry contracts and produces
V3 decisions/intents. It does not know V2 classes, V2 state, V2 globals or
legacy execution. The package has no import path to `application` or `runtime`.

### Safety

The flow is explicit:

```text
Telemetry/SafetySignal -> V3 SafetyDomain -> Containment ActuatorIntent
                         -> V3 ExecutionDispatcher -> shadow adapter
```

The shadow adapter returns `executed=False`. It cannot issue OFF, STOP, HA,
ESPHome or RD commands.

### Configuration

The V3 core rejects unknown keys and validates typed defaults. The current
schema is deliberately a migration schema, not a claim that every existing V2
value has been canonically resolved. Project-wide YAML/Python/env/persisted
conflicts therefore remain a production migration blocker.

### Composition

`V3Composition.standalone()` is the only composition root inside the pure
package. Construction performs no I/O, worker creation, persistence or
hardware access. It is not wired into `bot.py`.

## Legacy elimination status

V2 remains available as parity/replay reference in the repository, but it was
not imported by `v3_core`. Existing V2 physical paths were not deleted in this
controlled preparation because deletion without a validated replacement could
remove the only currently proven fail-safe path.

Required before physical elimination:

1. exact V3 adapter contract against the target RD/ESPHome node;
2. readback and verified-OFF parity;
3. lease/dead-man parity and failure tests;
4. rollback and restart evidence;
5. supervised physical bench gate;
6. separately authorized production cutover.

## Stage status

| Stage | R4 |
|---|---|
| Stage 0 — current V2 / V3 shadow | PASS |
| Stage 1 — V3 decision ownership | BLOCKED |
| Physical execution migration | BLOCKED |
| Legacy physical path removal | BLOCKED |

## Verification

- V3 core tests: 5 OK;
- Workstream 3 tests: 5 OK;
- V3 core `compileall`: OK;
- `git diff --check`: OK.

Conclusion: the standalone pure-core objective is met; the requested
production Architecture PASS and legacy physical elimination are not claimed
without the required safety and bench evidence.
