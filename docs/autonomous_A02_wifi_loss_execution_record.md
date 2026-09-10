# AUTONOMOUS A02 Wi-Fi-loss execution record

This record validates loss and restoration of the home control plane after A01
has passed. It records evidence only; it does not change authority or safety
behavior. For a failure, use the canonical
[`autonomous_hardware_failure_capture.md`](autonomous_hardware_failure_capture.md)
form and stop testing.

## Identification

- Date/time (UTC): `________________________________________`
- Operator: `________________________________________`
- Location: `________________________________________`
- Bot SHA: `________________________________________`
- ESPHome firmware SHA: `________________________________________`
- RD model: `________________________________________`
- RD firmware: `________________________________________`

## Preconditions

Record before each subtest:

- Mode: `AUTONOMOUS`
- Ownership provenance: `AUTONOMOUS`
- Confidence: `VERIFIED`
- Output state: `ON / OFF`
- Edge mode/generation/lease/trip: `________________________________________`
- RD V/I/protection readback: `________________________________________`
- Emergency disconnect available: `YES / NO`

Do not proceed unless the autonomous bit and fresh edge evidence are positively
confirmed. Do not infer ownership from Wi-Fi state or RD V/I.

## A02.1 — AUTONOMOUS, Output OFF, Wi-Fi OFF

### Procedure

1. Enter AUTONOMOUS and verify the preconditions above.
2. Confirm and record Output OFF.
3. Disconnect Wi-Fi only.
4. Observe locally for the approved interval without issuing bot commands or
   changing mode, ownership, load or RD settings.
5. Record the first and last local readbacks, then restore Wi-Fi only as part
   of the documented test sequence.

### Acceptance

PASS requires no shutdown solely from Wi-Fi loss and no mode or ownership
change. FAIL on any autonomous shutdown, mode change or ownership loss not
caused by an independent physical safety event.

- Timestamp: `________________________________________`
- Expected: no shutdown; mode/ownership unchanged.
- Observed: `________________________________________`
- OwnershipSnapshot: `________________________________________`
- Output: `________________________________________`
- Voltage: `________________ V`
- Current: `________________ A`
- Temperature: `________________ °C`
- Logs (Telegram / HA / ESP / RD): `________________________________________`
- Result: `PASS / FAIL / BLOCKED`

## A02.2 — AUTONOMOUS, Output ON, Wi-Fi OFF

### Procedure

1. Start from verified AUTONOMOUS ownership and an approved safe generic
   program; enable Output only through the approved autonomous/local procedure.
2. Confirm Output ON and capture local protection readback.
3. Disconnect Wi-Fi only.
4. Observe locally for at least 30 minutes; record periodic timestamps,
   Output, ownership and protection state.
5. Do not use the bot, change V/I, or modify the RD program during observation.

### Acceptance

PASS requires Output remains active under edge/RD control; no bot actuator
commands, managed lease shutdown or orphan shutdown occurs solely because
Wi-Fi is unavailable; and autonomous state remains preserved. FAIL on any such
intervention, state change or independent safety anomaly not separately
explained by evidence.

- Timestamp(s): `________________________________________`
- Expected: Output remains ON; no bot/lease/orphan intervention.
- Observed: `________________________________________`
- OwnershipSnapshot: `________________________________________`
- Output: `________________________________________`
- Voltage: `________________ V`
- Current: `________________ A`
- Temperature: `________________ °C`
- Logs (Telegram / HA / ESP / RD): `________________________________________`
- Result: `PASS / FAIL / BLOCKED`

## A02.3 — AUTONOMOUS, Output ON, Wi-Fi restored

### Procedure

1. Begin with the preserved AUTONOMOUS Output ON state from A02.2 and record
   the transport-down timestamp.
2. Restore Wi-Fi without changing the RD program, Output or mode.
3. Observe monitoring/telemetry recovery and record the first fresh readback.
4. Compare mode, generation, ownership and Output before and after recovery.
5. Verify logs contain no bot actuator command during recovery.

### Acceptance

PASS requires monitoring returns, mode remains AUTONOMOUS, ownership remains
AUTONOMOUS, and no automatic takeover or V/I/Output change occurs. FAIL if the
bot changes V/I, enables/disables Output, changes mode or adopts ownership.

- Timestamp(s): `________________________________________`
- Expected: monitoring resumes; ownership unchanged; no actuator command.
- Observed: `________________________________________`
- OwnershipSnapshot: `________________________________________`
- Output: `________________________________________`
- Voltage: `________________ V`
- Current: `________________ A`
- Temperature: `________________ °C`
- Logs (Telegram / HA / ESP / RD): `________________________________________`
- Result: `PASS / FAIL / BLOCKED`

## Failure handling

Stop testing immediately on:

- unexpected Output OFF;
- unexpected Output ON;
- ownership or mode change;
- managed authority appearing;
- missing or contradictory edge evidence.

Preserve logs, timestamps, snapshots, ESP/RD readbacks and the current state.
Do not toggle modes repeatedly. Return to a safe state using the documented
rollback procedure; do not treat Wi-Fi loss as authorization for takeover.

