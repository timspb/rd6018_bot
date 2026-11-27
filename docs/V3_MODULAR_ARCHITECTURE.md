# V3 Modular Architecture Contract

Status: **current production architecture contract**.

OVP/OCP are retained as physical configuration/readback and protection-diagnostic
signals. Preserve their entities, register 82/83 readbacks and the existing managed
software trip guard. The current HassClient / ESP Native physical adapter does not
expose OVP/OCP setters, so START and MAIN/MIX do not automatically program these
thresholds. A confirmed trip may stop an active PB_MANAGED session through the
existing safety owner; HANDS_OFF + AUTONOMOUS remains strictly read-only and cannot
issue a bot-originated stop. Preserve intrinsic local nonzero-R16 containment via
the integrated ESP8266 and the single R18 Output Owner. Do not disable or rewrite
the RD6018's physical protection thresholds.

The modular cutover is complete. Retired V1/V2 compatibility, shadow and dual-runtime
owners are not production architecture and must not be reintroduced.

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

## 2. Production module graph

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

Canonical production guard classes now live in `runtime/safety/runtime_guard.py`,
`runtime/safety/strict_guard.py`, and `runtime/safety/managed_guard.py`.
These are the existing safety-effect adapters, not additional execution owners.
Pure telemetry, electrical-envelope, foreign-Output, freshness and watchdog
policies live in separate sibling modules. `runtime/safety/watchdog_runtime.py`
provides one background observation task; the soft and 300-second
communication policies cannot issue competing OFF for a latched incident.
All actual actuator mutations still use the established application
`ExecutionPort` / physical bridge. No top-level runtime guard compatibility
modules exist.

The former mixed `safe_output.py` is split by concern: policy DTOs,
`SafetySupervisor` and telemetry snapshots have one owner in
`runtime/safety/output_policy.py`; the existing state-preserving verified
output-enable transaction lives in `application/safe_output_coordinator.py`.
It is the same established output adapter execution seam, not a second
hardware or charge-session owner. Source and physical-call inventories freeze
both paths and release D124 treats their changes as control changes.

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

## 5. Change rule

For each production boundary change:

1. identify the current owner and callers;
2. preserve safety, restart and failure semantics with focused tests;
3. change one authoritative route rather than adding a parallel owner;
4. remove only code proven unreachable or superseded;
5. keep static architecture guards that prevent retired compatibility routes from returning.

Do not create two active owners.

## 6. Compatibility facades are forbidden

Retired compatibility modules are deleted rather than kept as forwarding shims.
Production filenames and internal owner types must not reintroduce the retired
`v2_*` namespace. Historical-looking persisted/protocol/external telemetry identifiers
are separate compatibility boundaries and are changed only through an explicit migration.

No new legacy/compatibility import surface may be introduced. Callers move to
the current owner directly.

## 7. Completion criteria

Current production must continue to satisfy all of the following:

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

## Non-negotiable modularity and configuration canon (2026-11-07)

**No new monoliths.** This applies to all RD6018 changes, including operator HMI, charging algorithms, recovery, telemetry, logging, and release tooling. An existing oversized file is not a license to add another feature branch to it.

- One module owns each capability, state transition, clock, renderer, configuration value, and side effect. Separate read models, pure policy/formatting, orchestration, Telegram adapter, hardware execution, and persistence. Composition wires them; it must not reimplement their rules.
- Every user-tunable duration, threshold, limit, recipe parameter, choice, and policy belongs in the owning module's declared typed `variables.py` / `config.py` (or the canonical existing recipe/spec registry). Define units, default, range, provenance, override policy, and change effect. All consumers read that same definition; no scattered literals, shadow settings, duplicate copies, or hidden environment overrides.
- Presentational countdowns **derive** from the existing SignalAnalyzer/MAIN authority timestamps and configured hold duration. They never establish their own timer, storage, charge transition authority, or additional polling process. Different chemistry/intent must not be inferred from ad-hoc UI constants.
- Preserve exactly one Telegram panel lifecycle owner, one 60-second refresh task, and in-place edits. New UI features belong in focused read-model/presenter/component modules; the Telegram adapter stays transport-only. Do not expand `operator_hmi.py`, `runtime/production_runtime.py`, or `bot.py` with new cross-layer policy.
- Before each change: identify existing canonical owner and config source, perform the smallest source modification that implements the requirement, and remove superseded code rather than adding shims. Do not construct a parallel abstraction, extra proof/authorization, new service, duplicate observer, or alternative rollback path.
- Acceptance: focused module tests + existing architecture/UI regressions + actual entrypoint behavior where relevant. Record evidence and exact SHA in the runbook. Keep the deployed known-good baseline untouched until an explicit safe D145/D144 installation is authorized; never confuse source acceptance with live hardware/UI acceptance.
- If requested work needs a new setting or subsystem, extend the original semantic owner rather than opening an independent control plane. Reject any design that makes two modules authoritative for the same state.

## Execution owner encapsulation — 2026-11-15

`ExecutionPort` is the only application-facing physical execution boundary. Its composed Safety owner is private (`_execution_owner`); application consumers must not inspect or call it directly. Application read consumers use `ExecutionPort.read_live()` / `read_native_physical_output_report()`, while physical commands use the existing typed port operations. `HassClient` and the configured HA/ESP connector remain transport/read adapters. Production installs `ManagedRuntimeSafetyGuard` with `patch_adapter=False`; the optional adapter-patching compatibility mode is not a production composition path.

Static architecture tests enforce that application modules other than `application/execution_port.py` do not access `.execution_owner` or `._execution_owner`. MAIN Guard transaction and recipe execution consume live snapshots through the port. This encapsulation does not move Safety policy into programs, nor does it make the port a charge-phase owner.
## Transport/Safety separation — 2026-11-15

`HassClient` is a raw transport adapter for HA REST and the selected physical connector. It owns connection/session management, raw telemetry metadata and raw command dispatch only. It does not own SafetySupervisor, SafeOutputCoordinator, programming admission, ON verification, OFF confirmation, lease policy or runtime protection.

`RuntimeSafetyGuard` / `ManagedRuntimeSafetyGuard` are explicit Safety owners over the injected `adapter`. They perform admission, lease, telemetry/protection, setpoint verification, Output verification and OFF containment. `ExecutionPort` privately owns the Safety execution owner and is the application-facing command/read boundary. Production installs the Safety owner without mutating adapter methods (`patch_adapter=False`).

HA REST `get_state()` is an independent sidecar when the selected physical connector has no native entity-state API. Native physical Output evidence remains sourced only from the selected physical connector and never falls back to HA. `last_reported` is part of HassClient's transport metadata contract; Safety must not monkeypatch the transport formatter.