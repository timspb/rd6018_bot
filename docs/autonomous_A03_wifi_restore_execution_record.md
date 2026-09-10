# AUTONOMOUS A03 Wi-Fi restore execution record

This record validates that restoration of the control plane restores observation only. It must not transfer ownership from the edge back to the bot.

Use with [the hardware failure capture form](autonomous_hardware_failure_capture.md). Stop the test on any unexpected actuator or ownership change.

## Identification

- Date/time:
- Operator:
- Location:
- Bot software SHA:
- ESPHome firmware SHA:
- RD6018 model:
- RD firmware:

## Preconditions

Record the state immediately before Wi-Fi is disconnected:

- Operation mode: `AUTONOMOUS`
- Ownership provenance: `AUTONOMOUS`
- Confidence: `VERIFIED`
- Output state: `ON`
- Voltage:
- Current:
- Temperature:
- OwnershipSnapshot:
- Edge autonomous state / acknowledgement:
- Observation interval while offline (planned and actual):
- Emergency disconnect available: yes / no

Do not begin A03 unless AUTONOMOUS ownership is explicitly acknowledged and the precondition snapshot is complete.

## Procedure

1. Run the RD6018 in `AUTONOMOUS` with Output ON.
2. Verify and record the precondition OwnershipSnapshot and RD readback.
3. Disconnect Wi-Fi. Record the exact loss timestamp.
4. Wait for the defined observation interval; record telemetry and logs without issuing control commands.
5. Restore Wi-Fi. Record the exact restoration timestamp.
6. Observe bot reconnection and the return of fresh monitoring only. Do not request adoption, managed mode, restore, or any actuator action.
7. Capture the post-recovery OwnershipSnapshot, edge state, RD readback, and command/log evidence.
8. Compare the before/after records and complete the result section.

## PASS criteria

PASS only when all applicable evidence shows:

- mode remains `AUTONOMOUS`;
- ownership provenance remains `AUTONOMOUS`;
- confidence remains valid (`VERIFIED` when the edge supplies fresh verification);
- no automatic transition to `PB_MANAGED` occurs;
- no automatic session restore occurs;
- no bot actuator command is issued;
- voltage, current, setpoints, and Output do not change because of Wi-Fi recovery;
- monitoring resumes without an ownership takeover.

Any independent physical-safety intervention must be recorded separately with its triggering evidence; it is not evidence of a successful A03 run.

## FAIL criteria

FAIL and stop testing if any of the following occurs:

- the bot takes ownership automatically;
- a managed session starts automatically;
- the bot issues an Output, voltage, current, or setpoint command;
- Output changes unexpectedly;
- voltage or current changes because of reconnection;
- AUTONOMOUS state or ownership is lost;
- the bot performs automatic restore or takeover after reconnect.

## Evidence capture

- Test start timestamp:
- Wi-Fi lost timestamp:
- Wi-Fi restored timestamp:
- Observation interval:
- Observed bot reconnect / fresh monitoring:
- OwnershipSnapshot before:
- OwnershipSnapshot after:
- Output before:
- Output after:
- Voltage before / after:
- Current before / after:
- Temperature before / after:
- Commands observed:
- Managed-session or lease events:
- Edge state / acknowledgement:
- Telegram/operator log:
- HA/control-plane state:
- ESP state:
- RD telemetry/readback:
- Other logs:

## Result

| Check | Expected | Observed | Evidence | PASS/FAIL |
|---|---|---|---|---|
| Mode after recovery | `AUTONOMOUS` | | | |
| Ownership after recovery | `AUTONOMOUS` | | | |
| Confidence after recovery | valid / verified | | | |
| Automatic PB_MANAGED transition | none | | | |
| Automatic restore/takeover | none | | | |
| Bot actuator commands | none | | | |
| Output and V/I | unchanged | | | |
| Monitoring | resumed | | | |

Overall result: PASS / FAIL

Notes:

## Recovery on failure

If A03 fails:

1. Stop the test immediately.
2. Preserve logs, telemetry, timestamps, screenshots, and both OwnershipSnapshots.
3. Do not repeat Wi-Fi toggles or continue relocation tests.
4. Complete [the hardware failure capture form](autonomous_hardware_failure_capture.md).
5. Return through the documented OFF-only transition before returning to `PB_MANAGED`; do not use network recovery as an ownership transition.

## Review note

Wi-Fi restoration permits monitoring to resume. It does not grant the bot ownership, authorize automatic takeover, or imply a managed charging-session restore.
