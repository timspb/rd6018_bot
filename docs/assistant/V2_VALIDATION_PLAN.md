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
| Mix maxima Ca20/EFB24/AGM10 | production timing tests | SW-PASS |
| Mix timeout is `MIX_TIMEOUT -> STOP_AND_DIAGNOSE`, never SAFE_WAIT success | authority + production-composition integration tests | SW-PASS |
| Mix authority uses durable active time and freezes proven-OFF intervals | durable clock/restart tests | SW-PASS |
| missing/corrupt/mismatched Mix authority cannot be reconstructed from Ah | durable authority fail-close tests | SW-PASS |
| adaptive Mix current ratchet can only tighten and has no default actuator authority | containment persistence/monotonicity tests | SW-PASS |
| SAFE_WAIT max 2h anti-stall | state-machine tests | SW-PASS |
| Cooling freezes active clocks | cooling persistence/runtime tests | SW-PASS |
| Done/Storage means Output ON only for normal completion | completion/controller tests | SW-PASS |
| Auto Mix direct entry + timeout wording | mix-only tests | SW-PASS |
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
| failed OFF remains containment authority even if legacy chemistry state is already retired | V2 runtime OFF-unconfirmed retry regressions | SW-PASS |
| recovery start/complete/abort cannot retire authority before verified OFF | RecoveryOrchestrator containment regressions | SW-PASS |
| diagnostic task cancellation after a current step restores the original current or forces OFF before cancellation escapes | probe cancellation cleanup regressions | SW-PASS |
| edge lease software geometry is 15 min / 5 min and requires positive ACK | Python + ESPHome contract tests | SW-PASS |
| active HANDS_OFF release uses dedicated edge ownership transfer, session-bound confirmation and renewal serialization | D060 Python + exact ESPHome contract regressions | SW-PASS |
| HANDS_OFF cannot revive stale AUTO authority and post-commit lost edge ACK never silently rolls back to PB | D060 ownership/restart containment regressions | SW-PASS |
| external-temp Class-C detector has no uncalibrated production thresholds | integrity monitor/runtime tests | SW-PASS |

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
18. Characterize external-temperature registers 34/35 and `temp_ext_v2` across stable probe, deliberate disconnect/reconnect, connector disturbance and real heating/cooling. Record source timestamps even when the value is flat; only these traces may activate Class-C N/range/step/slope or a hard disconnect sentinel.

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
- inject unavailable/stale confirmation and verify fail-closed reporting;
- additionally emulate the legacy exception path that retires the chemistry controller after a failed OFF attempt: V2 runtime containment must **not** enter ordinary orphan grace, must retain `OFF unconfirmed`, and must retry verified shutdown until Output is physically confirmed OFF;
- after delayed successful OFF confirmation, verify the containment flag clears and the edge lease is disarmed only after OFF proof.

### C3 communication loss — 15/5 lease
Test the exact branch package after the current occupied hardware experiment is finished:
- compile/flash the 900000 ms ESPHome lease together with the bot 300 s renewal cadence;
- one missed 5-minute renewal must not itself trip while adequate lease remains;
- sustained bot/HA/network loss with low-energy output;
- sustained loss with >15V output;
- process kill while output active;
- ESP/bridge restart;
- RD power cycle;
- prove local repeated OFF occurs no later than 15 minutes after the **last positively acknowledged** controller heartbeat;
- prove late recovery remains trip/quarantine-safe and cannot silently resume the old charge.

No native RD6018 timer write is part of this gate. If one is added later, first prove its semantics separately and prove it cannot stack another 15-minute authority window after the edge deadline.

### C4 Mix timeout actuator path
Use a shortened **test-only** Mix limit on a dummy/safe load; do not change production chemistry constants merely to make the test short.
- enter Mix through managed output;
- do not generate finish evidence;
- exhaust the test active-time ceiling;
- require exact reason `MIX_TIMEOUT`;
- verify no SAFE_WAIT/Storage success transition occurs;
- verify Output OFF is physically confirmed;
- inject delayed/failed OFF and prove `_off_unconfirmed` containment continues until OFF proof.

### C5 Mix durable active-time clock
With a shortened test configuration and an external trace clock:
- active Mix ON consumes budget;
- Cooling/proven Output OFF does not consume budget;
- resume continues from the same remaining budget;
- restart while durable state was active conservatively consumes outage time;
- restart after durable inactive state does not consume outage time;
- remove/corrupt/mismatch the durable authority file and verify Mix/Cooling-from-Mix restore is rejected rather than reconstructed from Ah.

### C6 HANDS_OFF live ownership transfer
Use the exact Python commit and exact flashed ESPHome package on a dummy/load-safe setup before relying on D060 in production.
- establish a managed session with Output ON and record V/I/OVP/OCP, edge generation and lease state;
- press the first HANDS_OFF action only and prove nothing actuates;
- change/replace the managed session before Execute and prove the old confirmation is rejected;
- repeat with the same session and Execute the release;
- prove Output and V/I/OVP/OCP remain unchanged through the transfer;
- prove the dedicated `Safety Lease Release To Hands Off` command, not normal `Safety Lease Disarm`, is used;
- prove edge generation changes, managed lease becomes unarmed, trip/quarantine remain clear and managed remaining time becomes zero;
- prove ordinary Disarm still refuses to clear a managed lease while Output is ON;
- race a 5-minute renewal with the release and prove no renewal can re-arm the lease after successful transfer;
- suppress/delay release ACK after the edge command and prove software stays durable HANDS_OFF rather than silently restoring PB authority; local watchdog behavior must be explicitly observed;
- kill/restart the bot after durable HANDS_OFF and prove stale pre-release AUTO state does not regain software authority;
- return Pb control only after raw Output OFF is confirmed and prove no old AUTO session resumes automatically;
- verify explicit HANDS_OFF Output OFF still uses raw command + positive OFF readback and does not itself return PB authority.

Required state for D060 physical deployment claim: **BENCH-PASS**. Until then D060 is software-implemented only.

Required state before merge: **BENCH-PASS**.

## D. Diagnostic restart / cancellation bench gate

1. Start a controlled diagnostic current probe on dummy load/controlled setup.
2. Kill the bot after current has been lowered but before normal restoration.
3. Restart.
4. Verify journal marks action `ABORTED_RESTART`.
5. Verify no mid-probe setpoint restoration is attempted after process restart.
6. Verify Output is forced/remains OFF and operator is notified.
7. Verify a completed probe remains durable evidence and is not rewritten as interrupted.
8. Separately cancel the live diagnostic task (without killing the process) after the current step. Before `CancelledError` escapes, verify the original current is restored and read back; if restoration is unavailable/mismatched, Output must be positively confirmed OFF.
9. Repeat cancellation with restore failure plus OFF failure and verify software does not report a successful cleanup/forced-OFF condition.

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
Use a battery already suitable for Mix entry and >=12V. Verify direct Mix session, active-time accounting, evidence handling and normal final Storage. Verify <12V is rejected without PREP fallback using a safe simulated/bench input if possible rather than abusing a deeply discharged battery.

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

### G3 Mix adaptive-current containment — `OPEN-CAL`

The durable ratchet exists and is SW-PASS, but its production actuator authority remains intentionally disabled. Using real Q005/Q014 and Mix traces, establish:
- what constitutes a confirmed `Imin` for containment authority;
- required finish/reversal `ΔI` under actual measurement resolution;
- capacity-scaled/relative term and absolute hardware floor;
- containment headroom that remains safely above the finish signal;
- exact condition for `CURRENT_CEILING_REACHED` / censored evidence;
- safe current + OCP tightening order and fresh configured readback;
- behavior across CV->CC when the tightened ceiling is reached;
- restart/network-loss proof that a tighter local ceiling can never be silently enlarged.

Only after these are characterized may the ratchet be connected to RD current/OCP writes. Until then `MixContainmentPolicy()` has no production headroom and reports `actuator_authority=False`.

### G4 Resolved manufacturer/product boundaries — software contract, not OPEN-CAL

- **EFB upper envelope (D054):** generic AUTO/Recovery/Conditioning <=16.5V. A global `expert` flag cannot enlarge it. 17.5V remains Manual/Custom outer authority. Future >16.5V automatic EFB requires an exact model-specific manufacturer-backed profile.
- **SG policy (D053):** physical access is explicit; AGM never SG; EFB/Ca/Flooded require `SERVICEABLE`; raw is primary evidence; manufacturer correction is explicit; temperature-compensated hydrometer is never double-corrected.

These are no longer open questions and must not be reintroduced as merge blockers unless new evidence requires a numbered Decision Log revision.

## H. Final merge review

Before marking PR ready:

```text
software CI exact head         PASS
all required BENCH gates       PASS
required real-battery traces   PASS
15/5 lease physical proof      PASS
HANDS_OFF live-release proof   PASS
Mix timeout/off-path proof     PASS
Mix active-time restart proof  PASS
Q004/Q013 calibration evidence reviewed
Q005/Q014 characterization reviewed / auto trigger remains fail-closed if unresolved
adaptive current actuation remains disabled unless G3 is calibrated and BENCH-PASS
external-temp Class-C authority remains disabled unless its physical calibration is complete
Decision Log / Open Questions  synchronized
PR body                         synchronized
main                            still untouched
```

Only then move PR from Draft to Ready for Review. Merge still requires explicit operator approval.
