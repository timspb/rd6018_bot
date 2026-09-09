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

# Safety invariants

Always active:

- RD internal temperature protection;
- absolute voltage limits;
- absolute current limits;
- power/thermal protection;
- hardware fault handling.

Never weaken these while adding autonomous mode.

---

# Autonomous contract

AUTONOMOUS means:

RD6018 can operate as a general programmable power supply.

Allowed loads:

- batteries;
- electronics;
- motors;
- lamps;
- laboratory loads;
- arbitrary DC equipment.

Not assumed:

- Pb chemistry;
- charging algorithm;
- battery sensor;
- Telegram;
- HA;
- Wi-Fi.

---

# Repair phases

## Phase 1 — Domain separation

Status: IN PROGRESS

Add explicit concepts:

- ownership;
- operation mode;
- operating state.

No runtime behavior changes.

---

## Phase 2 — Runtime safety separation

Pending.

Audit:

- orphan output handling;
- controller_active;
- telemetry requirements;
- lease enforcement.

Goal:

MANAGED keeps current fail-closed behavior.

AUTONOMOUS does not fail only because control plane disappeared.

---

## Phase 3 — ESPHome contract

Pending.

Required:

- persistent local operating mode;
- managed lease behavior unchanged;
- autonomous mode not dependent on Wi-Fi heartbeat;
- local physical safety retained.

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

---

# Forbidden fixes

Do not implement:

- unlimited orphan timeout;
- global safety bypass;
- RD_ALLOW_UNMANAGED_OUTPUT style switches;
- disabling fail-closed globally;
- treating V=0/I=0 as proof of OFF;
- auto-adoption of arbitrary external charge states.

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
