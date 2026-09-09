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

### Immediate actions

Do not start a new charge session.

Collect:

- Output state freshness;
- protection status;
- edge lease state;
- last ownership transition;
- persisted RD mode.

### Expected recovery choices

1. Adopt ownership only through the explicit live-adoption contract.
2. Release to HANDS_OFF through the ownership transfer contract.
3. Verified Output OFF.

Do not use direct setpoint writes.

---

## INC-002 — HANDS_OFF active but control must return

### Preconditions

- Operator intentionally released RD ownership.
- Pb automation is not owner.

### Recovery

Require:

- verified Output OFF;
- fresh telemetry;
- new Pb authorization;
- fresh safety preflight.

Do not revive an old session.

---

## INC-003 — Wi-Fi/network loss during managed charge

### Expected behavior

The edge lease is authoritative.

On communication loss:

- renewals stop;
- lease expiry leads to local containment;
- late application recovery must not silently resume charging.

### Investigation

Check:

- lease generation;
- last ACK;
- Modbus freshness;
- controller session state.

---

## INC-004 — Telemetry stale or unknown

### Rule

Unknown is not OFF.

Do not infer:

- Output state;
- protection state;
- regulation mode.

Recovery:

1. Restore telemetry.
2. Verify direct device state.
3. Resume only through normal authorization.

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

# Debug checklist

```text
1. Is physical Output state known?
2. Is protection state fresh?
3. Who is current owner?
4. Is edge lease armed?
5. Is there a valid session identity?
6. What was the last ownership transition?
7. What recovery path is explicitly authorized?
```

# Development rules after incidents

Fixes must preserve:

- ownership boundaries;
- edge safety lease semantics;
- physical readback requirements;
- production composition order.

Prefer repairing boundaries over adding bypass flags.
