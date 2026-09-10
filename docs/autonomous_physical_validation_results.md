# AUTONOMOUS physical validation results

This ledger is completed from the real RD6018 hardware run. It accepts
evidence only; it does not grant authority, change software behavior or
replace the [master validation run](autonomous_full_field_validation_run.md).

## Run Identity

- Validation date/time (UTC):
- Operator:
- Location:
- RD model:
- RD firmware:
- ESPHome firmware SHA:
- ESP device identity:
- Bot SHA:
- Session/evidence archive ID:

## Baseline

- Software baseline SHA:
- Mode before test:
- Ownership provenance before test:
- Confidence before test:
- Output state:
- Voltage:
- Current:
- Temperature:
- Emergency disconnect available: `YES / NO`
- Baseline evidence references:

Every value below must identify its source and timestamp. Use `UNKNOWN` or
`UNAVAILABLE` when a value was not observed; never substitute an inferred or
zero value.

## Test Results

| Test | Expected | Observed | Evidence | Result |
|---|---|---|---|---|
| A01 AUTONOMOUS entry | Explicit ACK, persistent autonomous state, verified autonomous OwnershipSnapshot, no managed actuator authority | | | `PASS / FAIL / BLOCKED` |
| A02.1 Wi-Fi loss, Output OFF | No shutdown, mode change or ownership loss solely from Wi-Fi loss | | | `PASS / FAIL / BLOCKED` |
| A02.2 Wi-Fi loss, Output ON | Output remains edge-controlled; no bot, lease or orphan shutdown | | | `PASS / FAIL / BLOCKED` |
| A03 Wi-Fi restore | Monitoring resumes; AUTONOMOUS ownership remains; no takeover or actuator command | | | `PASS / FAIL / BLOCKED` |
| A04 autonomous reboot | Deterministic autonomous persistence and safe startup; no managed recovery | | | `PASS / FAIL / BLOCKED` |
| A05 local safety | Internal/RD protection remains active with the documented safe response | | | `PASS / FAIL / BLOCKED` |
| A06 return to managed | Output OFF → explicit acknowledgement → `PB_MANAGED`; no surprise resume | | | `PASS / FAIL / BLOCKED` |
| A07 relocation | Operation continues without home Wi-Fi/HA/Telegram and without bot takeover | | | `PASS / FAIL / BLOCKED` |

Missing required evidence is `BLOCKED`, not `PASS`.

## Evidence Attachments

Complete one block for each test and subtest.

### Test: `__________`

- Timestamp start/end (UTC):
- Procedure variant:
- Source(s): `RD / ESP / HA / bot log / Telegram / instrument / operator`
- Logs:
- Telemetry (voltage/current/temperature):
- Output readback:
- Mode and generation:
- OwnershipSnapshot:
- Commands observed:
- Protection state:
- Screenshots/readbacks:
- Operator notes:
- Evidence archive path/reference:

Repeat the block for A01, A02.1, A02.2, A03, A04, A05, A06 and A07.

## Classification

Classify a failure only when the evidence distinguishes the cause. Do not
guess between software, firmware, hardware and setup.

| Classification | Required evidence |
|---|---|
| `EXPECTED` | Observed behavior matches the frozen software/edge contract. |
| `SOFTWARE DEFECT` | Exact software baseline violates the contract with valid firmware and setup evidence. |
| `FIRMWARE DEFECT` | Exact ESPHome firmware violates the edge contract with valid software and setup evidence. |
| `HARDWARE ISSUE` | RD, wiring, load or physical protection is independently evidenced as the cause. |
| `OPERATOR/SETUP ISSUE` | Identity, preconditions, wiring, procedure or evidence capture was invalid. |

- Classification:
- Evidence supporting classification:
- Reviewer:

## Final Decision

- Decision: `PASS / BLOCKED / FAIL`

`PASS` requires all A01–A07 results to be PASS with complete evidence.

`BLOCKED` means required evidence is missing or ambiguous; it is not a defect
classification.

`FAIL` requires a verified defect with evidence and a completed failure report.

- A01–A07 gate summary:
- Failure report reference, if any:
- Final notes:
- Operator sign-off:
- Reviewer sign-off:
