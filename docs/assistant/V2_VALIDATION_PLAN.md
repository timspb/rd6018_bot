# V2 Pre-Merge Validation Plan

This is the gate checklist for PR #2. Passing normal unit CI is necessary but **not sufficient** to merge V2 to `main`.

Decision authority remains `V2_DECISION_LOG.md`. This file records how accepted behavior must be proven.

## Gate states

- `SW-PASS` — deterministic software/CI coverage exists and passes.
- `BENCH-PASS` — verified on RD6018/dummy load or controlled lab setup.
- `BAT-PASS` — verified on a real battery trace where battery chemistry is required.
- `OPEN-CAL` — numeric calibration/policy intentionally unresolved.

PR must remain Draft while any required BENCH/BAT gate is missing.

## A. Software authority gates

| Contract | Required evidence | State |
|---|---|---|
| initial `<12V PREP / >=12V MAIN` before first ON | AUTO strategy/startup tests | SW-PASS |
| Normal full AUTO vs Diagnostic no-auto-HV | strategy/recipe/controller tests | SW-PASS |
| Ca/EFB 3-attempt session budget | controller/strategy tests | SW-PASS |
| AGM 4-attempt conservative budget | controller/strategy tests | SW-PASS |
| 72h Main fallback | deterministic strategy tests | SW-PASS |
| Mix CV/CC evidence + sticky 2h | Mix/evidence tests | SW-PASS |
| Mix fallback Ca20/EFB24/AGM10 | production timing tests | SW-PASS |
| SAFE_WAIT max 2h anti-stall | state-machine tests | SW-PASS |
| Cooling freezes active clocks | cooling persistence/runtime tests | SW-PASS |
| Done/Storage means Output ON | completion/controller tests | SW-PASS |
| Auto Mix direct entry | mix-only tests | SW-PASS |
| AUTO Manual-OFF is terminal side-condition only | isolation tests | SW-PASS |
| Manual is sole managed manual authority | entrypoint/manual tests | SW-PASS |
| Manual V/I <=17.5V/12A, derived OVP/OCP | manual/safety tests | SW-PASS |
| active Manual reconfiguration verified OFF -> fresh ON | manual runtime tests | SW-PASS |
| Manual optional battery identity does not alter V/I | manual context tests/review | SW-PASS |
| persisted Manual -> INTERRUPTED -> explicit reauth | restart/reauth tests | SW-PASS |
| battery-bound parser precedes generic numeric Manual parser | middleware precedence regression | SW-PASS |
| diagnostic action restart matrix | journal/restart tests | SW-PASS |
| diagnostic inference cannot create HARD_STOP | fault-engine tests | SW-PASS |
| SG first imbalance is not short-cell proof/HV veto | diagnostics tests | SW-PASS |

## B. Exact ESPHome/RD telemetry bench gates

Use the exact production ESPHome node/config, not a synthetic register mock.

1. Compile and flash exact node config.
2. Record RD6018 model, serial, firmware and calibration fingerprint.
3. Verify corrected temperature decoding at positive values and, if safely reproducible, negative external-probe value/sign behavior.
4. Verify Pout entity against displayed RD power and `V_OUT * I_OUT` within expected quantization.
5. Trigger/observe protection status mapping where safely possible; prove `3` is not decoded as simultaneous OVP+OCP.
6. Verify CV/CC state transition against RD front panel/load behavior.
7. Verify configured readback for V/I/OVP/OCP after writes.
8. Verify `BAT_MODE` is observational and does not create a software start gate.
9. Verify Boot Power / Take Out safe configuration on the actual device.

Required state before merge: **BENCH-PASS**.

## C. Actuator transaction / edge-fail-close bench gates

Use a dummy load or otherwise non-battery hazardous setup first.

### C1 safe enable
- command legal V/I;
- verify OVP/OCP written first as required;
- verify configured values read back;
- verify Output ON only after successful transaction;
- inject one failed/mismatched readback -> Output must remain/become OFF.

### C2 verified OFF
- command OFF;
- prove physical/output entity OFF confirmation path;
- inject unavailable/stale confirmation and verify fail-closed reporting.

### C3 communication loss
Test at least:
- HA/API loss with low-energy output;
- HA/API loss with >15V output;
- process kill while output active;
- ESP/bridge restart;
- RD power cycle.

Expected: higher-energy state gets the shortest blind-operation tolerance and edge lease removes sustained uncontrolled output.

Required state before merge: **BENCH-PASS**.

## D. Diagnostic restart bench gate

1. Start a controlled diagnostic current probe on dummy load/controlled setup.
2. Kill the bot after current has been lowered but before normal restoration.
3. Restart.
4. Verify journal marks action `ABORTED_RESTART`.
5. Verify no mid-probe setpoint restoration is attempted.
6. Verify Output is forced/remains OFF and operator is notified.
7. Verify a completed probe remains durable evidence and is not rewritten as interrupted.

Required state before automatic probe policy is enabled: **BENCH-PASS**.

## E. Manual restart / identity bench gate

1. Create saved physical battery record.
2. Start Manual bound to that identity with arbitrary legal operator V/I.
3. Prove selected battery chemistry/Ah does not alter requested V/I.
4. Kill bot while Manual active.
5. Restart and verify Output is not silently enabled and state is `INTERRUPTED`.
6. Review saved request in Telegram.
7. Re-authorize; verify full fresh safe-enable/readback transaction and fresh active-time clock.
8. Delete/retire the saved battery record and verify stale bound request is not silently rebound to another battery.

Required state before merge: **BENCH-PASS**.

## F. Real-battery chemistry trace gates

Run with conservative known-good batteries first.

### F1 Ca/Ca or EFB normal AUTO
Capture:
- start decision PREP/Main;
- Main tail/progress;
- any plateau/recovery attempt;
- SAFE_WAIT round-trip;
- final Mix evidence;
- final SAFE_WAIT -> Storage.

### F2 AGM
Capture staged 14.4 -> 14.6 -> 14.8 -> 15.0 Main behavior and verify conservative recovery/timeout policy. Do not deliberately create a harmful stuck condition merely to exercise a transition.

### F3 Auto Mix
Use a battery already suitable for Mix entry and >=12V. Verify direct Mix session, evidence handling and final Storage. Verify <12V is rejected without PREP fallback using a safe simulated/bench input if possible rather than abusing a deeply discharged battery.

Required state before merge: **BAT-PASS** for representative standard AUTO and Auto Mix; AGM policy should have at least non-destructive trace confirmation.

## G. Open calibration gates — do not guess

### Q004/Q013 fault scoring
Need real traces with known outcomes before tuning `cell_fault`/other hypothesis thresholds.

### Q005/Q014 controlled probe / RD response
Need actual ESPHome sample cadence, ADC resolution/repeatability, current-step response, cable/clip reconnection effect and relay-path signal characterization. Automatic probe trigger remains disabled until this is measured.

### Q011 expert EFB 17.2–17.5V
No standard recipe permission exists. Requires explicit manufacturer/evidence policy, strict time/current/thermal limits and fresh per-run authorization.

### Q012 SG policy
Raw SG remains authoritative evidence storage. Manufacturer/hydrometer temperature correction and proactive prompt policy must be defined before corrected SG is used for decisions.

These stay `OPEN-CAL` and do not get closed by unit tests.

## H. Final merge review

Before marking PR ready:

```text
software CI exact head         PASS
all required BENCH gates       PASS
required real-battery traces   PASS
open-cal features              disabled/fail-closed unless explicitly resolved
Decision Log / Open Questions  synchronized
PR body                         synchronized
main                            still untouched
```

Only then move PR from Draft to Ready for Review. Merge still requires explicit operator approval.
