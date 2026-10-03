# V3 Modular Architecture Contract

Status: **authoritative target architecture** for the V3 migration.

This document supersedes the old idea that V3 may remain a compatibility shell
around the V1/V2 runtime. Compatibility code may exist only while a bounded
migration step is being proven. It must not be the final owner of a migrated
capability.

## 1. Non-negotiable rule

A migrated V3 capability is implemented by a V3 module, not by:

- calling `runtime.v2_runtime` and renaming the result;
- subclassing the historical FSM and masking selected transitions;
- changing `stage_start_time`, blanking or another input merely to stop the old
  algorithm from firing;
- monkey-patching a shared runtime module with `install_*` wrappers;
- keeping a hidden direct hardware fallback behind an optional V3 route;
- rendering V3 UI from legacy runtime globals.

The historical implementation can be used as a **test oracle** until parity is
proved. Once a boundary is migrated, its old production route is removed.

## 2. Target module graph

```text
bot.py
  -> composition root
      -> application
      -> charge domain
      -> signal/evidence
      -> safety
      -> execution
      -> telemetry
      -> ownership/session
      -> persistence
      -> UI
      -> infrastructure adapters
```

Only the composition root wires modules. It contains no charge rules, safety
thresholds, UI handlers, persistence policy or physical calls.

### Application

Owns use cases, intents, orchestration and correlation. It does not own charger
algorithms or transport calls.

### Charge domain

Owns program and stage decisions. Required modules are at least:

- PREP;
- MAIN;
- DESULFATION / bounded recovery;
- MIX;
- SAFE_WAIT;
- STORAGE / DONE;
- COOLING;
- Manual/Custom as a separate program family.

Each stage consumes immutable state + evidence + typed configuration and
returns a decision/effects object. It never writes to RD6018.

### Signal/evidence

Owns CV/CC interpretation, Imin, Vmax, Delta-I, Delta-V, confirmation spacing,
plateau evidence, active-time clocks and restartable evidence snapshots.

### Safety

Safety is modular by concern:

- thermal;
- telemetry freshness;
- voltage/current envelope;
- OVP/OCP;
- startup settling and programmed readback;
- communication loss;
- watchdog/containment;
- edge lease.

Charge policy cannot bypass safety. Safety does not choose charge stages.

### Execution

There is exactly one application-to-physical execution owner. All hardware
mutations are expressed as typed execution intents. The execution transaction
owns ordering, verification, containment and commit.

No logger, Telegram callback, stage object, restore helper or watchdog may call
RD setters directly after its boundary has been migrated.

### UI

UI is a first-class modular layer. See `V3_UI_MODULAR_ARCHITECTURE.md`.

### Persistence

Every durable object has an owner, schema version and restore policy. Persisted
state alone never authorizes Output ON after restart.

## 3. Configuration and variable ownership

Every behavioral/configuration value belongs to exactly one module.

A module that owns configurable values stores their declarations in its own
`variables.py` or `config.py`. There is no general bag of unrelated magic
constants.

Every declared variable must include:

- stable key/name;
- type;
- unit, or explicit `dimensionless`;
- Russian/English-neutral technical description;
- semantic owner/module;
- default or statement that no default exists;
- minimum/maximum or allowed enum where meaningful;
- provenance;
- override policy;
- whether changing it is runtime-safe, restart-required or deployment-only.

Consumers receive typed configuration from the owner. They do not copy the
number into another module.

A shared `VariableSpec` type may define metadata shape, but it must not become
a central place that owns unrelated values.

## 4. UI-specific invariant

No new button, callback, screen, graph control or operator text requires a
change in charge, safety, execution or monolithic runtime code.

UI action flow:

```text
ButtonSpec -> UIAction -> Application Intent -> Application Service
```

Never:

```text
button/callback -> hass/set_voltage/turn_on/controller internals
```

## 5. Migration rule

For each boundary:

1. capture old behavior with golden/characterization tests;
2. implement the modular V3 owner without importing the legacy implementation;
3. compare decisions/effects;
4. prove restart/failure semantics;
5. switch one production route;
6. delete or make unreachable the old production route;
7. add a static test proving the legacy route cannot return.

Do not leave two active owners after cutover.

## 6. Legacy is allowed only as bounded debt

Every remaining compatibility seam must be listed in
`V3_LEGACY_ERADICATION_LEDGER.md` with:

- current owner;
- why it is still reachable;
- replacement module;
- removal gate;
- status.

New unlisted legacy dependencies fail review.

## 7. Completion criteria

V3 is complete only when production satisfies all of the following:

- `bot.py` is a small composition/lifecycle entrypoint;
- no production import of `runtime.v2_runtime`, `bot_legacy` or historical
  charge FSM;
- no production `super().tick()` into the historical FSM;
- one FSM owner;
- one execution owner;
- one safety decision boundary with modular safety concerns;
- one physical transaction path;
- one source of truth for each configurable value;
- UI consumes canonical read models and emits application intents only;
- buttons/callbacks are declarative UI modules;
- no module-global monkey-patched application object;
- restart cannot re-enable Output without fresh physical authorization;
- full Python 3.10/3.11/3.12 CI and hardware validation gates pass.
