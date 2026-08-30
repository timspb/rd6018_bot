# V2 Pre-Merge Validation Plan

This is the gate checklist for PR #2. Passing normal unit CI is necessary but **not sufficient** to merge V2 to `main`.

Decision authority remains `V2_DECISION_LOG.md`. This file records how accepted behavior must be proven.

## Gate states

- `SW-PASS` — deterministic software/CI coverage exists and passes.
- `BENCH-PASS` — verified on RD6018/dummy load or controlled lab setup.
- `BAT-PASS` — verified on a real battery trace where battery chemistry is required.
- `OPEN-CAL` — numeric calibration intentionally unresolved and remains fail-closed/disabled where required.

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
| SG physical access + hydrometer/correction policy | SG policy/UI/store tests | SW-PASS |
| generic EFB expert flag cannot exceed 16.5V | recipe envelope + hardware-isolation regressions | SW-PASS |
| labeled Bank-Fault calibration replay/reporting | calibration harness tests | SW-PASS |
| read-only dynamic-loop bench capture | source-time/dedup/no-actuation capture tests | SW-PASS |
| raw dynamic-loop characterization math/reporting | characterization harness tests | SW-PASS |
| managed runtime rejects stale/incoherent Vbat/I/T and energized V_OUT | runtime freshness + verified-OFF regressions | SW-PASS |
| managed runtime rejects stale Output/protection authority | switch + raw/legacy protection freshness regressions | SW-PASS |
| managed chemistry evidence rejects stale CV/CC source | raw/legacy regulation freshness regressions | SW-PASS |
| production managed runtime rejects missing `_meta` rather than degrading to value-only safety | runtime metadata-required regression | SW-PASS |
| unchanged dynamic/status values use HA `last_reported`, not stale `last_updated` | telemetry heartbeat regressions | SW-PASS |
| HA bulk and per-entity fallback preserve equivalent `last_reported` heartbeat semantics | HassClient fallback regressions | SW-PASS |
| bulk `/api/states` failure uses concurrent batched per-entity fallback | fallback batching regression | SW-PASS |
| idle stale Vset/Iset/OVP/OCP timestamps do not block preflight | context-sensitive freshness regression | SW-PASS |
| freshly programmed Vset/Iset/OVP/OCP is required before/post ON | programmed-readback freshness regressions | SW-PASS |
| idle stale `V_OUT=0` heartbeat does not block preflight; energized stale V_OUT fails closed | VOUT context regression | SW-PASS |

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
10. Measure the actual timestamps/cadence delivered by the installed ESPHome/Modbus/HA path; do not assume a global 5s poll interval from template sensor snippets.
11. Hold dynamic/status values physically/numerically flat long enough that HA `last_updated` would otherwise stay old; verify `last_reported` continues to advance at the real integration reporting cadence for Vbat/current/temperature/V_OUT, Output, protection and CV/CC sources that are exposed by the exact node.
12. Fault-inject one critical physical source (prefer external battery temperature on dummy/safe setup) so its source heartbeat exceeds the 20s software freshness window; verify a managed energized session forces verified OFF. Separately prove an hours-old unchanged Vset/Iset/OVP/OCP timestamp does **not** create a false runtime freshness trip while values/readback remain valid.
13. Fault-inject stale status/evidence independently: stop reporting Output state, protection source (`protection_code` or both legacy OVP/OCP sensors), and regulation source (`regulation_code` or both legacy CV/CC sensors). Verify each becomes fail-closed instead of allowing stale ON/OFF, stale normal-protection or stale CV/CC evidence to continue driving runtime/FSM decisions.
14. Force/fake a bulk `/api/states` failure while individual `/api/states/<entity>` remains available. Verify fallback preserves `last_reported`, returns a coherent snapshot in one concurrent request batch, and does not create a false stale shutdown solely because the value has not changed.
15. With Output OFF and measured V_OUT stable at 0V long enough to have an old value-change timestamp, verify a new safe preflight remains possible. Then energize a dummy-load session and stop V_OUT reporting; energized stale/missing V_OUT must force verified OFF.
16. Verify a new start after hours of idle setpoints is permitted to enter the programming transaction, but suppress/hold back HA observation of one just-written V/I/OVP/OCP value and prove Output ON is denied until fresh programmed readback is observed.
17. Remove/corrupt `_meta` at the V2 adapter boundary in a controlled test while a managed dummy-load output is ON; verify production runtime fails closed instead of continuing from numeric values alone.

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
- any naturally occurring plateau/recovery attempt;
- SAFE_WAIT round-trip;
- final Mix evidence;
- final SAFE_WAIT -> Storage.

Do not deliberately create a harmful stuck condition merely to exercise Recovery/Mix.

### F2 AGM
Capture staged 14.4 -> 14.6 -> 14.8 -> 15.0 Main behavior and verify conservative recovery/timeout policy. Do not deliberately create a harmful stuck condition merely to exercise a transition.

### F3 Auto Mix
Use a battery already suitable for Mix entry and >=12V. Verify direct Mix session, evidence handling and final Storage. Verify <12V is rejected without PREP fallback using a safe simulated/bench input if possible rather than abusing a deeply discharged battery.

Required state before merge: **BAT-PASS** for representative standard AUTO and Auto Mix; AGM policy should have at least non-destructive trace confirmation.

## G. Calibration gates — do not guess

### G1 Q004/Q013 fault scoring — `OPEN-CAL`

Tooling exists:

```bash
python tools/evaluate_battery_fault.py labeled-cases.jsonl --output report.json
```

Use `BANK_FAULT_CALIBRATION.md` for case schema/labeling. Before changing production weights/15-35-60-80 levels, collect real independently labeled healthy and fault cases.

Track separately:
- unexpected `BLOCK_AUTOMATIC_HV`;
- missed labeled `BLOCK_AUTOMATIC_HV`;
- per-hypothesis level mismatch.

Do not tune a single aggregate accuracy while hiding either safety-significant block error class.

### G2 Q005/Q014 controlled probe / RD response — `OPEN-CAL`

Read-only capture and offline analysis tooling exist. A characterization sequence is:

```bash
python tools/capture_dynamic_loop.py probe.jsonl \
  --phase baseline \
  --connection-id clips-a \
  --duration-s 120 \
  --truncate

# Manually reduce current to the selected safer characterization value.
# The capture tool itself MUST NOT actuate the RD6018.

python tools/capture_dynamic_loop.py probe.jsonl \
  --phase stepped \
  --connection-id clips-a \
  --duration-s 180

# Restore and verify the original current; optional evidence capture:
python tools/capture_dynamic_loop.py probe.jsonl \
  --phase restored \
  --connection-id clips-a \
  --duration-s 120

python tools/characterize_dynamic_loop.py probe.jsonl --output report.json
```

Use `DYNAMIC_LOOP_CALIBRATION.md`. The collector stores actual Vbat/current HA source timestamps and skew and discards duplicate source polls. It must reject missing source timestamps rather than turning the local polling cadence into fake measurement cadence.

Collect multiple raw baseline/step/restore traces and characterize:
- real cadence and source skew;
- Vbat/current MAD/span and observed value steps;
- actual measured `ΔI`/`ΔV`;
- settling trajectory;
- repeatability without reconnecting;
- change after clip/lead reconnection using a new `connection_id`;
- descriptive Vout-Vbat behavior;
- hardware/firmware/calibration identity.

Only then choose production `ProbePlan` amplitude/timing/readback/noise thresholds. Automatic trigger policy remains disabled until calibrated. The existence of the collector/analyzer is **not** a BENCH-PASS by itself.

### G3 Resolved manufacturer/product boundaries — software contract, not OPEN-CAL

- **EFB upper envelope (D054):** generic AUTO/Recovery/Conditioning <=16.5V. A global `expert` flag cannot enlarge it. 17.5V remains Manual/Custom outer authority. Future >16.5V automatic EFB requires an exact model-specific manufacturer-backed profile.
- **SG policy (D053):** physical access is explicit; AGM never SG; EFB/Ca/Flooded require `SERVICEABLE`; raw is primary evidence; manufacturer correction is explicit; temperature-compensated hydrometer is never double-corrected.

These are no longer open questions and must not be reintroduced as merge blockers unless new evidence requires a numbered Decision Log revision.

## H. Final merge review

Before marking PR ready:

```text
software CI exact head         PASS
all required BENCH gates       PASS
required real-battery traces   PASS
Q004/Q013 calibration evidence reviewed
Q005/Q014 characterization reviewed / auto trigger remains fail-closed if unresolved
Decision Log / Open Questions  synchronized
PR body                         synchronized
main                            still untouched
```

Only then move PR from Draft to Ready for Review. Merge still requires explicit operator approval.
