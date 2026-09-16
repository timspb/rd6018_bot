# RD6018 V3 runtime migration model — EPIC E

Status: runtime composition preparation. The V3 shell is shadow-only and does
not replace `bot.py`, V2 startup, V2 control, lease ownership or physical
execution.

## 1. Runtime ownership

| Area | Current owner | Target owner | EPIC E mode | Rollback |
|---|---|---|---|---|
| process/bootstrap | V2 `bot.py` and distributed installers | V3 composition root | parallel/shadow | keep V2 entrypoint |
| lifecycle | V2 startup/shutdown paths | `V3RuntimeComposition` shell | shadow | stop shell |
| domain/application graph | V2 active plus V3 shadow graph | V3 runtime composition | shadow | discard V3 decisions |
| telemetry/config/diagnostics | V3 staged boundaries; V2 consumers remain | V3 runtime shell | shadow | return V2 views |
| persistence | V2 runtime stores; V3 in-memory/candidate boundary | V3 adapter | shadow | do not restore V3 state |
| control/execution | V2 | V3 future boundary | not connected | V2 remains owner |
| physical output | V2/edge | V3 future approved owner | not connected | V2/edge unchanged |

Creating or starting the shell does not transfer ownership. Production cutover
requires a separate authorization and all prior EPIC gates.

## 2. V3 runtime shell

`application.runtime_composition.V3RuntimeComposition` owns only:

- startup lifecycle;
- dependency initialization and graph validation;
- shutdown lifecycle and worker cancellation;
- optional background shadow workers;
- diagnostics lifecycle events;
- health reporting;
- one shadow command/telemetry processing path.

It connects the existing `ApplicationComposition.shadow()` graph:

```text
V3RuntimeComposition
  +-- UI adapter
  +-- Application service
  +-- Domain runtime
  +-- Telemetry authority
  +-- Configuration authority/model
  +-- In-memory persistence boundary
  +-- Diagnostics domain
  +-- Shadow observer (injected)
  +-- Deferred execution/shadow adapters
```

The shell reports `physical_execution_enabled=False` unconditionally. It does
not import or start `bot.py`, V2 runtime bootstrap, HA clients, ESP clients or
physical adapters.

## 3. Lifecycle contract

```text
NEW -> STARTING -> RUNNING -> STOPPING -> STOPPED
                  |
                  +-----------------> FAILED
```

Startup creates the shadow composition when not injected, validates all
required dependencies, emits a diagnostic event and starts only explicitly
injected shadow workers. Shutdown cancels those workers, emits a diagnostic
event and leaves the V2 runtime untouched. Failed startup is reported through
health and does not attempt physical recovery.

Health must expose:

- lifecycle state;
- dependency readiness;
- running worker count;
- diagnostics readiness;
- observer connection state;
- explicit shadow-only and physical-disabled flags;
- last startup error, if any.

## 4. Migration modes

| Mode | V3 runtime behavior | V2 owner | Exit/rollback |
|---|---|---|---|
| parallel | shell exists beside V2 but receives no production control | V2 | stop shell |
| shadow | shell processes mirrored/synthetic input and records evidence | V2 | discard V3 results |
| staged | future restricted runtime handoff with explicit gate | V2 until approved | return to V2 |
| cutover | separately authorized V3 runtime owner | V3 only after approval | verified rollback to V2 |
| rollback | shell stopped/disabled; V2 resumes as sole owner | V2 | no implicit session resume |

EPIC E implements only parallel/shadow modes.

## 5. Dependency and worker rules

Dependencies are initialized through the single shadow composition root. No
worker may create a second composition, import production bootstrap, invoke a
control provider, renew a lease, write HA/ESP, or call a physical method.

Workers are optional and injected for tests/observation. Their cancellation
is part of shutdown; a worker failure cannot grant control ownership or trigger
a new physical shutdown owner.

## 6. Acceptance and readiness

EPIC E shadow acceptance requires:

1. startup creates or accepts a complete dependency graph;
2. startup/shutdown are idempotent and workers are cancelled;
3. health accurately reports lifecycle and shadow-only status;
4. one shadow command can traverse UI → application → domain → diagnostics;
5. telemetry is read-only and source/arbitration evidence is preserved;
6. persistence remains candidate/in-memory only;
7. the optional shadow observer is injected, not a runtime owner;
8. no HA/ESP writes, control calls or physical calls are reachable;
9. V2 bot, START, ACTIVE and physical ownership remain unchanged.

Overall readiness: `SHADOW_RUNTIME_READY`, `NOT_READY_FOR_CUTOVER`.

## Explicit non-goals

This EPIC does not replace the V2 bot, change startup order, enable START or
ACTIVE, connect HA/ESP control, execute `ActuatorIntent`, alter lease/safety
behavior, write persistence state, or perform physical output.

