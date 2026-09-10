# First AUTONOMOUS bench run sheet

This sheet covers only A01–A03. It is a physical validation procedure, not an
authority bypass. Use the operator checklist and baseline capture first. Stop
on any unexpected Output change, missing acknowledgement, ambiguous ownership
or unclear protection behavior.

## Preconditions

- Record the exact software and ESPHome firmware SHAs.
- Confirm the exact RD6018 node and load are identified.
- Confirm the emergency disconnect is reachable.
- Start at `PB_MANAGED` with Output positively confirmed `OFF`.
- Back up runtime state using the approved procedure.
- Record the initial `OwnershipSnapshot`, direct Output/protection readback,
  timestamps and evidence locations.

## A01 — Enter AUTONOMOUS

### Before

Expected state: `PB_MANAGED`, Output `OFF`, no active managed charge session.

Capture:

- mode and ownership readback;
- Output OFF and protection readback;
- current generation/timestamp;
- operator confirmation and baseline screenshot/log.

### During

1. Perform the existing explicit operator action to enter AUTONOMOUS.
2. Wait for the positive edge acknowledgement.
3. Record mode, generation and persistence readback.
4. Use only a safe non-actuating bot probe to confirm actuator commands are
   rejected; do not send V/I/OVP/OCP writes or start Pb charging.

### After

PASS requires:

```text
mode:       AUTONOMOUS
provenance: AUTONOMOUS
confidence: VERIFIED
```

and a persistent autonomous state with no bot actuator authority.

FAIL on missing ACK, non-persistent state or an accepted bot actuator command.
Keep Output OFF, stop the campaign and follow the rollback procedure in the
main bench plan.

## A02 — Wi-Fi loss

Run both variants independently. Record a timestamped `OwnershipSnapshot`,
direct Output/protection readback and relevant host/edge logs before, during and
after each variant.

### A02.1 — AUTONOMOUS, Output OFF, Wi-Fi OFF

#### Before

Expected state: AUTONOMOUS, autonomous provenance with verified confidence,
Output OFF and fresh edge acknowledgement. Capture mode, ownership,
generation, Output and protection state.

#### During

1. Disconnect Wi-Fi only.
2. Observe locally for the approved interval without issuing bot commands or
   changing the RD program.
3. Record periodic mode, ownership and Output evidence.

#### After

PASS: no shutdown solely due to Wi-Fi loss; mode remains AUTONOMOUS and
ownership remains autonomous. FAIL: mode/ownership changes or an autonomous
shutdown is attributed solely to Wi-Fi loss. Keep the device safe, restore
connectivity only as directed, preserve evidence and stop.

### A02.2 — AUTONOMOUS, Output ON, Wi-Fi OFF

#### Before

Expected state: AUTONOMOUS with verified autonomous provenance, approved safe
generic program, Output ON and local protection readback. Capture the exact
start timestamp and emergency-disconnect readiness.

#### During

1. Disconnect Wi-Fi while leaving the RD program and load unchanged.
2. Observe locally for at least 30 minutes.
3. Record Output, protection, mode, ownership and timestamps. Do not use the
   bot to intervene.

#### After

PASS: Output continues under edge/RD control; the bot does not intervene and
no managed lease/orphan shutdown occurs solely because Wi-Fi is unavailable.
FAIL: bot/runtime disables autonomous Output or changes ownership without an
explicit action. Use the emergency disconnect if required, preserve logs and
stop testing.

## A03 — Wi-Fi restore after AUTONOMOUS operation

### Before

Expected state: AUTONOMOUS, autonomous provenance, the same generation and
Output state as the end of A02.2. Capture the last offline snapshot/readback
and transport-down timestamp.

### During

1. Restore Wi-Fi without changing the RD program, Output or mode.
2. Observe monitoring/telemetry recovery and record the first fresh readback.
3. Compare mode, ownership, generation and Output before and after recovery.
4. Confirm no bot actuator command was emitted during recovery.

### After

PASS: monitoring returns; ownership remains AUTONOMOUS; generation/mode do not
change automatically; no V/I/OVP/OCP or Output command is issued and no
automatic takeover occurs.

FAIL: the bot changes V/I, enables/disables Output, changes mode or adopts
ownership automatically. Preserve timestamps, snapshots, logs and the failure
report; do not continue the campaign.

## Acceptance result table

| Test | Expected | Observed | PASS/FAIL | Evidence |
|---|---|---|---|---|
| A01 Enter AUTONOMOUS | Explicit ACK, persistent autonomous state, verified autonomous snapshot, bot actuator probes rejected | | | |
| A02.1 AUTONOMOUS + Output OFF + Wi-Fi OFF | No shutdown, mode and ownership unchanged | | | |
| A02.2 AUTONOMOUS + Output ON + Wi-Fi OFF | Output continues; no bot, lease or orphan intervention solely from Wi-Fi loss | | | |
| A03 Wi-Fi restore | Monitoring resumes; autonomous ownership remains; no actuator command or takeover | | | |

## Stop and recovery

Any failed criterion is a hard stop. Do not attempt a second run to explain an
ambiguous result. Disable AUTONOMOUS only through the existing explicit edge
procedure, return to `PB_MANAGED` only after positively verified Output OFF and
edge acknowledgement, and preserve logs, telemetry, timestamps, snapshots and
the failure report.

