# AUTONOMOUS physical evidence checklist

Use this checklist during the real RD6018 bench run. It collects evidence
needed to unblock physical AUTONOMOUS validation; it does not grant authority,
change mode or replace the [master validation run](autonomous_full_field_validation_run.md).

Do not classify a failure from a screenshot, graph or single host status alone.
Every observation requires a timestamp, source, observed value, expected value
and result.

## Identity

- RD model:
- RD firmware version:
- ESP device name:
- ESPHome firmware SHA:
- ESPHome flash date/time:
- Physical location:
- Operator:
- Bench session ID:
- Emergency disconnect available: `YES / NO`

## Software baseline

- Bot Git SHA:
- Branch:
- Deployment date/time (UTC):
- Current operation mode:
- Initial ownership provenance:
- Initial confidence:
- Initial Output state:
- Baseline evidence location:

## Evidence rule for every observation

Complete this block for each readback, command, log event and state change.

- Timestamp (UTC):
- Source: `RD / ESP / HA / bot log / Telegram / instrument / operator`
- Observed value:
- Expected value:
- Result: `PASS / FAIL / UNKNOWN`
- Evidence reference:
- Notes:

If a value is unavailable, write `UNAVAILABLE`; do not substitute zero or an
inferred value.

## A01 — Enter AUTONOMOUS

Starting state must be `PB_MANAGED` with positively verified Output `OFF`.

Collect:

- Transition request timestamp and operator action:
- Output before:
- Output after:
- Edge ACK (mode, generation, timestamp):
- Persistent autonomous state readback:
- OwnershipSnapshot before:
- OwnershipSnapshot after:
- Bot actuator-authority check:
- Related logs and screenshots:

Expected result:

- mode = `AUTONOMOUS`;
- provenance = `AUTONOMOUS`;
- confidence = `VERIFIED`;
- persistent state is present after reread/reboot boundary used by the test;
- no managed actuator authority remains.

Result: `PASS / FAIL / UNKNOWN`

## A02 — Wi-Fi loss

Record the autonomous precondition snapshot before each variant.

### A02.1 — Output OFF

- Wi-Fi disconnect timestamp:
- Observation interval:
- Output state:
- Voltage/current/temperatures:
- OwnershipSnapshot:
- Mode:
- Logs during outage:
- Result: `PASS / FAIL / UNKNOWN`

Expected: no shutdown, mode change or ownership loss solely because Wi-Fi is
offline.

### A02.2 — Output ON

- Wi-Fi disconnect timestamp:
- Observation interval (planned/actual):
- Output state at start/end:
- Voltage/current/temperatures at start/end:
- OwnershipSnapshot at start/end:
- Lease/orphan events:
- Bot actuator commands observed:
- Logs during outage:
- Result: `PASS / FAIL / UNKNOWN`

Expected: Output remains controlled by the autonomous edge; no bot command,
managed lease shutdown or orphan shutdown occurs solely because Wi-Fi is
offline.

## A03 — Wi-Fi restore

- Wi-Fi loss timestamp:
- Wi-Fi reconnect timestamp:
- First fresh monitoring timestamp:
- OwnershipSnapshot before:
- OwnershipSnapshot after:
- Mode before/after:
- Output before/after:
- Voltage/current before/after:
- Proof no managed takeover occurred:
- Proof no bot actuator command occurred:
- Reconnect and monitoring logs:
- Result: `PASS / FAIL / UNKNOWN`

Expected: monitoring resumes; mode and ownership remain `AUTONOMOUS`; no
automatic PB_MANAGED transition, restore, takeover, setpoint change or Output
command occurs.

## A04–A07 evidence references

Record the evidence archive location for the remaining cases in the master
run record:

- A04 — ESP reboot:
- A05 — local safety:
- A06 — return to `PB_MANAGED`:
- A07 — relocation without home Wi-Fi/HA/Telegram:

Use [the full field validation run](autonomous_full_field_validation_run.md)
for the procedure, expected behavior, stop conditions and acceptance matrix.

## Evidence quality review

Before classifying any result, confirm:

- timestamps are consistent across RD, ESP and host logs;
- the exact firmware and software identities are recorded;
- Output state comes from direct RD/edge readback where available;
- ownership comes from `OwnershipSnapshot` and explicit edge state, not V/I or
  Wi-Fi presence;
- commands are checked in bot and edge logs;
- missing data is marked `UNKNOWN` or `UNAVAILABLE`.

## Failure classification

Do not assign a category until the evidence set is complete.

| Classification | Use only when evidence proves |
|---|---|
| `EXPECTED` | Observed behavior matches the frozen software/edge contract. |
| `SOFTWARE DEFECT` | The exact software baseline violates its documented contract while firmware/setup evidence is valid. |
| `FIRMWARE DEFECT` | The exact ESPHome firmware violates the edge contract with valid software and setup evidence. |
| `HARDWARE ISSUE` | RD, wiring, load or physical protection behavior is independently evidenced as the cause. |
| `OPERATOR/SETUP ISSUE` | Preconditions, identity, wiring, procedure or evidence capture were invalid. |

Classification: `EXPECTED / SOFTWARE DEFECT / FIRMWARE DEFECT / HARDWARE ISSUE / OPERATOR/SETUP ISSUE / UNCLASSIFIED`

## Stop and recovery

Stop immediately on unexpected Output ON/OFF, ownership change, managed
takeover, missing autonomous persistence or ambiguous protection behavior.
Preserve this checklist, logs, telemetry, screenshots and timestamps. Complete
the [hardware failure capture form](autonomous_hardware_failure_capture.md)
and follow the documented OFF-only rollback before returning to managed mode.
