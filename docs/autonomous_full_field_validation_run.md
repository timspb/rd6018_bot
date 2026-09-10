# AUTONOMOUS full field validation run

This is the master operator record for the complete first physical validation
sequence A01–A07. Complete one copy during the real hardware run. The detailed
A01, A02 and A03 records remain evidence attachments; this document is the
operator entry point.

AUTONOMOUS is a general-purpose RD6018 operation mode, not Pb charging,
`HANDS_OFF`, an ownership bypass or a safety bypass. Use the existing
[`RD6018 AUTONOMOUS boundary`](RD_AUTONOMOUS_MODE.md) and stop on any ambiguous
authority or protection result.

## 1. Baseline

### Software

- Git SHA:
- Deployment date/time (UTC):

### ESPHome

- Firmware SHA:
- Flash date/time (UTC):

### RD6018

- Model:
- Firmware:
- Connected load:

### Initial state

- Operation mode: `PB_MANAGED / HANDS_OFF / AUTONOMOUS`
- Ownership provenance: `BOT_MANAGED / FOREIGN_OBSERVED / AUTONOMOUS / UNKNOWN`
- Confidence: `VERIFIED / OBSERVED / UNKNOWN`
- Output: `ON / OFF / UNKNOWN`
- Voltage:
- Current:
- PSU temperature:
- Load/battery temperature (if present):
- Active sessions:
- Edge state, generation and acknowledgement:
- Emergency disconnect available: `YES / NO`
- Baseline evidence locations:

Do not begin the sequence unless the initial state and direct RD/edge
readbacks are recorded. A01 must begin with `PB_MANAGED` and positively
verified Output `OFF`.

## 2. Test matrix

| Test | Scenario | Expected | Observed | Result |
|---|---|---|---|---|
| A01 | Enter `AUTONOMOUS` from `PB_MANAGED`, Output OFF | Explicit edge ACK, persistent autonomous state, verified autonomous provenance, no managed actuator authority | | `PASS / FAIL / BLOCKED` |
| A02.1 | `AUTONOMOUS` + Output OFF + Wi-Fi loss | No shutdown, mode change or ownership loss solely from Wi-Fi loss | | `PASS / FAIL / BLOCKED` |
| A02.2 | `AUTONOMOUS` + Output ON + Wi-Fi loss | Output remains controlled; no bot, lease or orphan shutdown | | `PASS / FAIL / BLOCKED` |
| A03 | Wi-Fi restore after autonomous operation | Monitoring resumes; autonomous ownership remains; no takeover or actuator command | | `PASS / FAIL / BLOCKED` |
| A04 | ESP reboot while autonomous | Deterministic autonomous persistence and startup; no managed recovery or unsafe transition | | `PASS / FAIL / BLOCKED` |
| A05 | Local safety validation | Internal/RD protection remains active; safe documented response | | `PASS / FAIL / BLOCKED` |
| A06 | Return to `PB_MANAGED` | Output OFF → explicit edge acknowledgement → managed state; no surprise resume | | `PASS / FAIL / BLOCKED` |
| A07 | Relocation without home Wi-Fi, HA or Telegram | Operation continues under explicit edge/local protection without bot takeover | | `PASS / FAIL / BLOCKED` |

For A01–A03, attach the detailed records:

- [`autonomous_A01_execution_record.md`](autonomous_A01_execution_record.md)
- [`autonomous_A02_wifi_loss_execution_record.md`](autonomous_A02_wifi_loss_execution_record.md)
- [`autonomous_A03_wifi_restore_execution_record.md`](autonomous_A03_wifi_restore_execution_record.md)

## A01 Physical Evidence

Complete this block during the first real hardware execution. A01 is not
`PASS` without explicit edge acknowledgement, persistent autonomous state,
an OwnershipSnapshot and evidence that no unexpected actuator command occurred.

### Identity

- Date/time (UTC):
- Operator:
- Location:
- RD model:
- RD firmware:
- ESPHome firmware SHA:
- Bot SHA:

### Initial state

- Mode:
- OwnershipSnapshot:
- Confidence:
- Output state:
- Voltage:
- Current:
- Temperature:

### Transition

- Command timestamp (UTC):
- Edge ACK timestamp (UTC):
- Persistent autonomous state confirmation (timestamp/readback):
- Edge generation / acknowledgement evidence:
- Bot actuator-authority check:

### After transition

- Mode:
- OwnershipSnapshot:
- Confidence:
- Output state:
- Telemetry (voltage/current/temperature):
- Unexpected actuator command observed: `YES / NO`
- Evidence locations (logs/readbacks/screenshots):

### Result

- Result: `PASS / FAIL`
- Notes:

If any required evidence is missing, record `UNKNOWN` and do not mark A01
`PASS`. For a failed or ambiguous result use the canonical
[`autonomous_hardware_failure_capture.md`](autonomous_hardware_failure_capture.md)
form.

## 3. Evidence record for each test

Duplicate this block for every A01–A07 case and subcase.

### Test: `__________`

- Start timestamp (UTC):
- End timestamp (UTC):
- Scenario / precondition:
- OwnershipSnapshot before:
- OwnershipSnapshot after:
- Mode before / after:
- Output before / after:
- Telemetry before / during / after (V, A, temperature):
- Edge state, generation and ACK:
- Commands observed:
- Lease/orphan/managed-authority events:
- Logs:
- Screenshots/readbacks:
- Operator notes:
- Result: `PASS / FAIL / BLOCKED`

Missing evidence is not a pass. Use
[`autonomous_hardware_failure_capture.md`](autonomous_hardware_failure_capture.md)
for any failed or ambiguous result.

## 4. Stop conditions

Stop the entire validation run immediately on any of the following:

- unexpected Output OFF;
- unexpected Output ON;
- any unexplained ownership or mode change;
- managed takeover or automatic adoption;
- lost or contradictory autonomous persistence;
- any bot actuator command during autonomous operation;
- safety or protection state is ambiguous;
- telemetry/readback is insufficient to establish the expected result.

Do not repeatedly toggle Wi-Fi, modes or Output to explain an ambiguous event.
Record the state first.

## 5. Recovery

Use the canonical
[`autonomous_hardware_failure_capture.md`](autonomous_hardware_failure_capture.md)
form and preserve logs, telemetry, timestamps, readbacks and screenshots.

```text
failure or ambiguity
        |
        v
      stop
        |
        v
 capture evidence
        |
        v
  safe rollback
```

Rollback sequence:

1. Stop the test and do not continue to the next case.
2. Preserve the complete evidence set and failure report.
3. Disable autonomous authority using the existing explicit edge procedure.
4. Return to `PB_MANAGED` only after Output `OFF` is positively verified and
   the required edge acknowledgement is received.
5. Do not use `HANDS_OFF` inference, a longer watchdog timeout or any safety
   bypass as recovery.

## 6. Final acceptance

Mark `AUTONOMOUS READY` only when every test has complete evidence and PASS:

| Acceptance gate | Result |
|---|---|
| A01 PASS | |
| A02.1 PASS | |
| A02.2 PASS | |
| A03 PASS | |
| A04 PASS | |
| A05 PASS | |
| A06 PASS | |
| A07 PASS | |
| No unresolved failure report | |
| Operator sign-off | |
| Reviewer sign-off | |

Final decision: `AUTONOMOUS READY / NOT READY / BLOCKED`

Final notes:
