# AUTONOMOUS field execution record

Use one copy of this record for the first physical RD6018 validation. This is
an evidence sheet, not permission to bypass an authority or safety gate.

## Session information

- Date/time (UTC): `________________________________________`
- Operator: `________________________________________`
- Location: `________________________________________`
- Test ID: `________________________________________`
- Git SHA: `________________________________________`
- ESPHome firmware SHA: `________________________________________`
- RD6018 model: `________________________________________`
- RD firmware: `________________________________________`
- Load connected: `________________________________________`

## Initial capture

Record direct readback and the read-only `OwnershipSnapshot` before testing.

- Mode: `PB_MANAGED / HANDS_OFF / AUTONOMOUS`
- Ownership provenance: `BOT_MANAGED / FOREIGN_OBSERVED / AUTONOMOUS / UNKNOWN`
- Confidence: `VERIFIED / OBSERVED / UNKNOWN`
- Output state: `ON / OFF / UNKNOWN`
- Voltage: `________________ V`
- Current: `________________ A`
- Temperature: `________________ °C`
- Active sessions: `________________________________________`
- Edge state (mode/generation/lease/trip): `________________________________________`
- Baseline logs/readbacks/screenshots: `________________________________________`

## A01 — Enter AUTONOMOUS

Starting state must be `PB_MANAGED` with Output positively confirmed `OFF`.

### Required evidence

- Operator command: `________________________________________`
- Edge ACK (mode/generation/timestamp): `________________________________________`
- Persistent autonomous state readback: `________________________________________`
- OwnershipSnapshot:

```text
mode:       AUTONOMOUS
provenance: AUTONOMOUS
confidence: VERIFIED
```

### Result

- Timestamp: `________________________________________`
- Observed: `________________________________________`
- Expected: explicit ACK, persistent autonomous state and rejected bot actuator commands.
- PASS/FAIL: `________________________________________`
- Evidence (Telegram log / HA state / ESP state / OwnershipSnapshot / RD telemetry): `________________________________________`

FAIL conditions: no ACK, state not persisted, or managed authority remains
active. Stop and use the documented rollback procedure.

## A02 — Wi-Fi loss matrix

Run each case separately. Do not change mode, ownership, RD program or load
between the recorded before/after observations except for the stated test
action.

### A02.1 — AUTONOMOUS, Output OFF, Wi-Fi OFF

Before: record a verified autonomous snapshot and fresh Output OFF readback.

During: disconnect Wi-Fi only; observe locally and record timestamped mode,
ownership and Output evidence. Do not issue bot commands.

Expected: no shutdown and no mode or ownership change solely from Wi-Fi loss.

- Timestamp: `________________________________________`
- Observed: `________________________________________`
- Expected: no shutdown; AUTONOMOUS ownership unchanged.
- PASS/FAIL: `________________________________________`
- Evidence (Telegram log / HA state / ESP state / OwnershipSnapshot / RD telemetry): `________________________________________`

### A02.2 — AUTONOMOUS, Output ON, Wi-Fi OFF

Before: record verified autonomous provenance, the approved safe generic
program, Output ON and local protection readback.

During: disconnect Wi-Fi and observe locally for at least 30 minutes. Do not
use the bot to intervene or change the RD program.

Expected: Output remains ON; no managed lease shutdown, orphan shutdown or bot
actuator command occurs solely because Wi-Fi is unavailable.

- Timestamp: `________________________________________`
- Observed: `________________________________________`
- Expected: Output continues; no lease/orphan shutdown; no bot commands.
- PASS/FAIL: `________________________________________`
- Evidence (Telegram log / HA state / ESP state / OwnershipSnapshot / RD telemetry): `________________________________________`

### A02.3 — AUTONOMOUS, Output ON, Wi-Fi restored

Before: retain the autonomous mode, generation, ownership and Output state from
A02.2; record the transport-down timestamp and last offline snapshot.

During: restore Wi-Fi without changing the RD program, Output or mode. Observe
the first fresh monitoring/readback and record any command activity.

Expected: monitoring resumes; ownership remains AUTONOMOUS; no automatic
takeover and no V/I/OVP/OCP or Output actuator command occurs.

- Timestamp: `________________________________________`
- Observed: `________________________________________`
- Expected: monitoring returns; ownership/mode unchanged; no actuator command.
- PASS/FAIL: `________________________________________`
- Evidence (Telegram log / HA state / ESP state / OwnershipSnapshot / RD telemetry): `________________________________________`

## Failure handling

If any test fails:

1. Stop the test campaign immediately.
2. Preserve logs, telemetry, timestamps, readbacks and screenshots.
3. Capture the current mode, ownership provenance, confidence, Output and edge state.
4. Do not toggle modes repeatedly or attempt to explain an ambiguous result by retrying.
5. Return to a safe state using the documented rollback procedure: disable
   AUTONOMOUS through the explicit edge procedure and return to `PB_MANAGED`
   only after positively verified Output OFF and edge acknowledgement.

## Session closeout

- Final mode: `________________________________________`
- Final ownership provenance/confidence: `________________________________________`
- Final Output/protection state: `________________________________________`
- Evidence archive: `________________________________________`
- Failure report required: `YES / NO`
- Operator sign-off: `________________________________________`
- Reviewer sign-off: `________________________________________`

