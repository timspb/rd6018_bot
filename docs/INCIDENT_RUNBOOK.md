# RD6018 Incident Runbook

## Purpose

This document is the operational runbook for RD6018 ownership, safety, and recovery incidents.
It describes containment and diagnosis. It is not an authority override.

Safety boundaries remain:

- fail closed on unknown critical telemetry;
- never silently resume old Pb authority;
- never bypass edge lease or readback checks;
- never treat UI state as physical state.

---

# Incident matrix

## INC-001 — Output ON but no managed charge session

### Symptoms

- RD6018 Output is ON.
- AUTO and MANUAL sessions are absent.
- Owner is unclear.

### Bounded ownership-decision window

When canonical Output is freshly confirmed ON but no managed software session exists, the host may leave the existing external program untouched only for the existing short orphan window (45 s) so ownership can be resolved.

This is **not** Pb authority and does not make the external program a valid managed charge. During this window:

- fresh canonical Output truth is mandatory;
- fresh RD protection evidence must be NORMAL;
- a positively observed internal PSU over-temperature remains immediate OFF authority;
- missing `temp_ext`, battery-voltage plausibility, Pb recipe setpoints/readbacks, and regulation mode are not used to seize the external program before ownership is chosen;
- the Pb edge lease is not renewed merely because the external Output was observed;
- expiry without an explicit ownership decision ends in verified Output OFF.

A stale/unknown Output or protection state, any RD protection trip, or expiry of the window is not graced. Selecting managed adoption still requires the full D061 battery/temperature/program/readback/TOCTOU preflight; the short decision window never satisfies or weakens that preflight.

### Recovery choices

1. Adopt ownership only through explicit live-adoption contract.
2. Release to HANDS_OFF through ownership transfer contract.
3. Verified Output OFF.

Do not use direct setpoint writes.

---

## INC-002 — HANDS_OFF active but control must return

Require:

- verified Output OFF;
- fresh telemetry;
- new Pb authorization;
- fresh safety preflight.

Do not revive an old session.

---

## INC-003 — Wi-Fi/network loss during managed charge

Expected:

- renewals stop;
- edge lease may expire;
- local containment may disable Output.

Investigate:

- lease generation;
- last ACK;
- Modbus freshness;
- controller session state.

---

## INC-004 — Telemetry stale or unknown

Unknown is not OFF.

Do not infer:

- Output state;
- protection state;
- regulation mode.

Recovery:

1. Restore telemetry.
2. Verify direct device state.
3. Resume only through authorization.

---

## INC-005 — Charge completed / restart recovery

Separate outcomes:

- successful Storage state;
- terminal stop;
- fault stop.

Never infer restart behavior from a generic DONE label alone.

Required evidence:

- completion reason;
- output intent;
- persisted session identity;
- fresh safety checks.

---

## INC-006 — Output OFF command not confirmed storm

### Severity

P0 control-plane failure.

### Symptoms

Repeated notifications:

```
Output OFF command not confirmed.
Further enable is blocked.
```

while telemetry may show:

```
Voltage: 0
Current: 0
Temperature: unavailable/0
Mode: unknown
```

### Classification

This is not automatically a hardware overcurrent/overvoltage event.

The system must distinguish:

```
OFF requested
 |
 +-- confirmed OFF
 |
 +-- confirmed ON -> safety fault
 |
 +-- UNKNOWN -> control-plane unavailable
```

### Forbidden behavior

Do not convert repeated readback uncertainty into an endless safety notification loop.

### Recovery

Collect:

- switch entity availability;
- HA connectivity;
- ESPHome connectivity;
- physical output readback;
- last safety decision reason.

After the first unresolved event:

- latch the incident;
- block unsafe re-enable;
- wait for operator or telemetry recovery.

Do not blindly repeat actuator commands.

---

## INC-007 — ESPHome offline / RD operation without Wi-Fi

### Severity

P1 operational availability, potentially P0 if combined with active charging.

### Symptoms

- RD6018 hardware is physically available.
- Wi-Fi is absent or unavailable.
- ESPHome safety component cannot renew/report lease state.
- Bot interprets missing network evidence as ownership/control failure.

### Required behavior

The ESPHome firmware must have a clearly defined offline operating contract.

Separate:

```
Wi-Fi unavailable
        !=
RD hardware unsafe
```

Offline mode must define:

- whether an already active output may continue;
- lease timeout behavior;
- local safety cutoff authority;
- local telemetry availability;
- recovery when Wi-Fi returns.

### Recovery plan

Firmware review required:

- remove accidental dependency on Home Assistant availability for safe local operation;
- keep local safety lease enforcement;
- expose local state needed for recovery;
- test boot and runtime behavior without Wi-Fi.

Do not bypass the safety lease. The goal is deterministic offline behavior, not disabling protection.

---

## INC-008 — adopted Manual was released to HANDS_OFF but stale D061 authority requests OFF

### Severity

P0 ownership-boundary failure if the external Output is still intentionally running.

### Symptoms

- a D061 Adopted Manual session was active;
- the operator explicitly released the running RD6018 to HANDS_OFF without changing Output/V/I/OVP/OCP;
- a later D061 monitor poll or process restart attempts verified Output OFF;
- or the D061 journal reappears as `OFF_PENDING` although durable HANDS_OFF owns the PSU.

### Classification

This is a split ownership-journal problem, not permission to weaken D061 restart containment globally.

The valid transaction is:

```
D061 ACTIVE + PB_MANAGED
        |
        | exact-session durable release intent
        v
D060 HANDS_OFF durable commit
        |
        v
D061 journal -> INTERRUPTED
Output/program unchanged
```

Before the durable HANDS_OFF commit, D061 remains managed safety authority. After the commit, only the exact matching release transaction may retire that same D061 OFF claim.

### Required behavior

- pre-commit failure keeps `PB_MANAGED` and ordinary D061 fail-closed restart/OFF semantics;
- a D061 state already in `OFF_PENDING` cannot be converted into HANDS_OFF release;
- generic HANDS_OFF alone is not proof that an adopted session was intentionally released;
- a stale or mismatched session marker grants no authority;
- HANDS_OFF plus the matching exact-session release marker may recover after crash by retiring D061 to `INTERRUPTED` without touching Output;
- ambiguous edge ACK after the durable HANDS_OFF commit must not resurrect D061 OFF authority or silently roll back to PB control.

### Recovery

Collect together:

- durable RD control mode;
- D061 adoption state and `session_id`;
- adopted-HANDS_OFF release-intent state and `session_id`;
- edge lease generation and release ACK evidence;
- canonical Output readback.

Do not manually delete journals or infer release from Output voltage/current. If durable ownership and exact-session evidence do not match, keep fail-closed containment and recover through verified Output OFF followed by a fresh ownership transaction.

---

# Debug checklist

```text
1. Is physical Output state known?
2. Is protection state fresh?
3. Who is current owner?
4. Is edge lease armed?
5. Is there a valid session identity?
6. What was the last ownership transition?
7. What recovery path is explicitly authorized?
8. Is OFF failure a device fault or an unavailable readback?
9. Is ESPHome behavior defined without Wi-Fi?
10. If D061 was released live, do durable HANDS_OFF and the exact release session agree?
```

# Development rules after incidents

Fixes must preserve:

- ownership boundaries;
- edge safety lease semantics;
- physical readback requirements;
- production composition order.

Prefer repairing boundaries over adding bypass flags.
