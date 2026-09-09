# RD6018 Autonomous Repair Incident Runbook

## Purpose

This document is the coordination source for the RD6018 autonomous-mode repair.

It is intentionally separate from Codex/repo-agent reports.

Use this file to track:

- confirmed incidents;
- root causes;
- invariants;
- decisions;
- completed repairs;
- remaining validation gates.

Do not mix implementation logs with incident conclusions.

---

# Incident: RD output unexpectedly disabled after leaving managed environment

## Symptoms

Observed:

- RD works while connected to home environment.
- RD moved to another location loses expected operation.
- Output can be disabled after control-plane loss.
- Repeated safety notifications can occur when OFF confirmation is unavailable.

Initial assumption "Wi-Fi loss is an RD hardware fault" is rejected.

The investigation target is the software ownership/safety boundary.

---

# Classification

## Confirmed classes

### C1 — Ownership/application policy mixed with hardware safety

Severity: HIGH

Problem:

The system currently combines:

- bot authority;
- charging application state;
- communication health;
- physical safety.

Required split:

```
Hardware safety
        !=
Application control
        !=
Control-plane availability
```

---

### C2 — HANDS_OFF is not a full operating mode

Severity: MEDIUM/HIGH

Current meaning:

- ownership release;
- bot actuator block.

It is not equivalent to:

- generic PSU autonomous operation.

Required model:

```
Ownership:
    BOT
    EXTERNAL

Operation:
    MANAGED
    AUTONOMOUS
```

The currently persisted software values map conservatively as follows:

```
PB_MANAGED -> BOT + MANAGED
HANDS_OFF  -> EXTERNAL + AUTONOMOUS
```

Unknown/corrupt values must never imply AUTONOMOUS.

---

### C3 — Pb application assumptions leak into generic PSU operation

Severity: HIGH

Managed Pb-only requirements must not terminate generic autonomous PSU use:

- charge session;
- chemistry profile;
- external battery temperature;
- restore state;
- Pb FSM.

---

### C4 — Accepted intrinsic software protection is not yet edge-local

Severity: HIGH

Confirmed current boundary:

- the accepted internal RD temperature cutoff is 55 C in host-side software;
- the canonical ESPHome telemetry package publishes internal temperature and raw
  protection status but does not itself perform the 55 C shutdown;
- the edge safety package currently performs communication/lease containment, not a
  complete generic-PSU hardware-safety policy.

Consequence:

AUTONOMOUS cannot be implemented safely as a blanket bypass of the runtime guard.
Intrinsic protection required during loss of Wi-Fi/HA must be moved or duplicated at
an edge-local authority before control-plane lease shutdown is disabled for that mode.

Do not invent new autonomous V/I/power thresholds. Use existing RD hardware protection
status where authoritative and existing accepted software limits where already defined.

---

# Safety invariants

Always active:

- RD internal temperature protection;
- configured/hardware OVP/OCP/OPP protection;
- hardware fault handling.

Do not silently reinterpret Pb working limits (16.6/17.5 V, 12 A) as generic PSU
hardware limits. Autonomous mode is load-agnostic and may use the native RD operating
range subject to its configured/intrinsic protection contract.

Never weaken intrinsic safety while adding autonomous mode.

---

# Autonomous contract

AUTONOMOUS means:

RD6018 can operate as a general programmable power supply.

Allowed loads:

- batteries of any chemistry;
- electronics;
- motors;
- lamps;
- heaters;
- laboratory loads;
- arbitrary DC equipment.

Not assumed:

- Pb chemistry;
- charging algorithm;
- battery sensor;
- Telegram;
- HA;
- Wi-Fi.

`temp_ext` is application telemetry in this mode. Missing/unavailable `temp_ext` is not
itself an autonomous fault. No generic emergency threshold is accepted until separately
validated; existing 35/40/45 C limits are Pb battery policy and must not be reused blindly.

---

# Repair phases

## Phase 1 — Domain separation

Status: DONE

Merged foundation:

- `RdOwnership`;
- `RdOperationMode`;
- `RdOperatingState`;
- supported-state validation;
- generic-PSU autonomous semantics;
- deterministic legacy control-mode mapping.

No actuator or ESPHome behavior is changed by this phase.

---

## Phase 2 — Runtime safety separation

Status: IN PROGRESS

Audit:

- orphan output handling;
- controller_active;
- telemetry requirements;
- lease enforcement;
- old `PB_MANAGED` / `HANDS_OFF` persistence bridge.

Goal:

MANAGED keeps current fail-closed behavior.

AUTONOMOUS does not fail only because control plane disappeared.

---

## Phase 3 — ESPHome contract

Status: DESIGN/IMPLEMENTATION NEXT

Required:

- persistent local autonomous authority, defaulting fail closed;
- managed lease behavior unchanged while MANAGED;
- autonomous mode not dependent on Wi-Fi/HA heartbeat;
- local internal-temperature cutoff retained without HA;
- raw RD OVP/OCP/OPP fault status remains safety authority;
- mode transition while Output ON is explicit and transaction-bound;
- reboot does not silently infer autonomous mode.

Edge transition invariants under review:

```
managed -> autonomous live release:
    healthy armed lease + fresh direct RD state
    -> preserve Output/setpoints
    -> persist autonomous ownership locally

autonomous -> managed live adoption:
    explicit adoption contract + fresh direct RD/protection evidence
    -> atomically retire autonomous edge state
    -> arm managed lease

unknown/corrupt edge mode:
    -> never infer autonomous
```

---

## Phase 4 — Validation

Required tests:

1. MANAGED + lost Wi-Fi keeps existing safety behavior.
2. AUTONOMOUS + no HA does not disable output solely for communication loss.
3. AUTONOMOUS + no temp_ext is valid.
4. AUTONOMOUS has no Pb restore/start path.
5. Bot cannot apply application setpoints in autonomous mode.
6. Corrupt mode state fails closed.
7. Reboot preserves deterministic mode behavior.
8. Internal RD overtemperature still causes local OFF without HA.
9. Raw OVP/OCP/OPP fault still causes local OFF.
10. Exact ESPHome target compiles; physical flash/bench loss tests remain separate gates.

---

# Forbidden fixes

Do not implement:

- unlimited orphan timeout;
- global safety bypass;
- RD_ALLOW_UNMANAGED_OUTPUT style switches;
- disabling fail-closed globally;
- treating V=0/I=0 as proof of OFF;
- auto-adoption of arbitrary external charge states;
- applying Pb chemistry ceilings as generic autonomous PSU hardware limits.

---

# Evidence separation rule

Codex reports:

- implementation findings;
- patches;
- test output.

This runbook:

- incident classification;
- architecture decisions;
- acceptance criteria.

They must not replace each other.
