# AUTONOMOUS A01 execution record

This is a fill-in operator record for the first physical validation of the
explicit `PB_MANAGED -> AUTONOMOUS` transition. It records evidence only and
does not grant authority or replace the approved safety procedure.

## Identification

- Date/time (UTC): `________________________________________`
- Operator: `________________________________________`
- Location: `________________________________________`
- Software SHA: `________________________________________`
- ESPHome SHA: `________________________________________`
- RD model: `________________________________________`
- RD firmware: `________________________________________`

## Initial state

Record the direct readback and read-only `OwnershipSnapshot` before the
transition.

- Before transition mode: `PB_MANAGED / HANDS_OFF / AUTONOMOUS`
- OwnershipSnapshot: `________________________________________`
- Output: `ON / OFF / UNKNOWN`
- Voltage: `________________ V`
- Current: `________________ A`
- Temperature: `________________ °C`
- Active sessions: `________________________________________`

Initial evidence locations (logs, readbacks, screenshots):
`________________________________________`

## A01 Steps

### Step 1 — Verify Output OFF

- Observed Output: `________________________________________`
- Protection/readback evidence: `________________________________________`
- Timestamp: `________________________________________`

### Step 2 — Request AUTONOMOUS transition

- Existing explicit operator action: `________________________________________`
- Timestamp: `________________________________________`

### Step 3 — Verify edge acknowledgement

- Acknowledgement received: `YES / NO`
- Acknowledgement mode/generation/timestamp: `________________________________________`
- Evidence location: `________________________________________`

### Step 4 — Verify persistent autonomous state

- Persistent mode: `________________________________________`
- Re-read after persistence interval: `________________________________________`
- Evidence location: `________________________________________`

### Step 5 — Verify OwnershipSnapshot

Expected read-only result:

```text
mode:       AUTONOMOUS
provenance: AUTONOMOUS
confidence: VERIFIED
```

- Observed OwnershipSnapshot: `________________________________________`
- Managed actuator authority absent: `YES / NO`
- Unexpected Output command observed: `YES / NO`
- Evidence location: `________________________________________`

## Acceptance

A01 is PASS only when all criteria are positively evidenced:

- mode is `AUTONOMOUS`;
- provenance is `AUTONOMOUS`;
- confidence is `VERIFIED`;
- no managed actuator authority remains;
- no unexpected Output command occurred.

| Criterion | Observed | PASS/FAIL | Evidence |
|---|---|---|---|
| Mode is AUTONOMOUS | | | |
| Provenance is AUTONOMOUS | | | |
| Confidence is VERIFIED | | | |
| Managed actuator authority absent | | | |
| No unexpected Output command | | | |

## Result

- A01 result: `PASS / FAIL / BLOCKED`
- Operator notes: `________________________________________`
- Evidence archive: `________________________________________`
- Operator sign-off: `________________________________________`
- Reviewer sign-off: `________________________________________`

## Failure and recovery

If any A01 criterion fails or ownership is ambiguous:

1. Stop testing immediately.
2. Capture logs, timestamps, readbacks, screenshots and the current
   `OwnershipSnapshot`.
3. Do not continue to Wi-Fi-loss tests.
4. Return through the documented OFF-only transition.
5. Preserve the complete evidence set and failure record.

Do not retry an ambiguous transition. Use the existing documented recovery
procedure and return to `PB_MANAGED` only after positively verified Output OFF
and edge acknowledgement.
