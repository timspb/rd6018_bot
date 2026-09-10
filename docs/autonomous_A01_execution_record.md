# AUTONOMOUS A01 execution record

The master operator entry point is [`autonomous_full_field_validation_run.md`](autonomous_full_field_validation_run.md); this document is the detailed A01 evidence attachment.

This is a fill-in operator record for the first physical validation of the
explicit `PB_MANAGED -> AUTONOMOUS` transition. It records evidence only and
does not grant authority or replace the approved safety procedure.

For any failed or ambiguous A01 result, use the canonical
[`autonomous_hardware_failure_capture.md`](autonomous_hardware_failure_capture.md)
form.

## Pre-flight

- Date/time (UTC): `________________________________________`
- Operator: `________________________________________`
- Location: `________________________________________`
- Bot SHA: `________________________________________`
- ESPHome firmware SHA: `________________________________________`
- RD model: `________________________________________`
- RD firmware: `________________________________________`
- Load: `________________________________________`
- Initial mode: `PB_MANAGED / HANDS_OFF / AUTONOMOUS`
- Initial ownership `OwnershipSnapshot`: `________________________________________`
- Output: `ON / OFF / UNKNOWN`
- Voltage: `________________ V`
- Current: `________________ A`
- Temperature: `________________ °C`
- Active sessions: `________________________________________`

Initial evidence locations (logs, readbacks, screenshots):
`________________________________________`

## Transition

Starting state must be `PB_MANAGED` with Output `OFF`.

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

## Evidence

Record the complete transition evidence:

- Timestamp(s): `________________________________________`
- Telegram/operator action: `________________________________________`
- ESP state (mode/generation/persistence): `________________________________________`
- Ownership state: `________________________________________`
- RD state (Output/V/I/protection): `________________________________________`
- Logs/readbacks/screenshots: `________________________________________`

## PASS

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

## FAIL

Stop immediately if any of these conditions occurs:

- no edge ACK;
- mixed authority;
- unexpected Output command;
- autonomous state is not persistent.

Do not retry an ambiguous transition. Preserve the evidence and use the
documented rollback procedure.

## A01 result

- Observed: `________________________________________`
- Expected: `________________________________________`
- Evidence: `________________________________________`
- Result: `PASS / FAIL / BLOCKED`
- Notes: `________________________________________`
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
