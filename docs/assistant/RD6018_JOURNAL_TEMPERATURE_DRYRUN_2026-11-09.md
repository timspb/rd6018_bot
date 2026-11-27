# RD6018 — MAIN/MIX operator journal and temperature provenance

## Scope and baseline — 2026-11-09

Source-only work in HOME-PC `E:\\CODEX\\rd6018_bot`, branch `feature/main-mix-countdown-display`, begun after commit `3b04f72`. No access to physical RD6018/ESP/HA actuators, no production node104 deployment, no change in charge chemistry, session state, thresholds, timers, equipment setpoints or execution-port authority.

The user's live evidence showed RD6018 `regulation_mode=cc`, `regulation_code=1`, `is_cv=0`, `is_cc=1`. The preceding source-only commit `3b04f72` repaired HMI mode presentation. This stage repairs the event journal; it does NOT resolve the physical 25°C versus Telegram 23°C discrepancy.

## Existing owners and exact changes

- `runtime/charge/evidence/trace_context.py`: signal analyzer's accepted Imin/Vmax, delta magnitudes, thresholds and confirmations are projected into existing observational events. One `log_event_sub` still uses the existing queue; no extra persistence mechanism or policy authority. The existing `build_signal_context` now includes analyzer-computed delta values for read-only checkpoint presentation.
- `runtime/charge/runtime/main_scaffold.py` and `mix_entry.py`: one MAIN→MIX effect preserves evidence at the actual decision edge, **before** the old MAIN stage clocks/references are reset. `MIX_STARTED` now includes the existing authority decision reason, target U/I, accepted Imin/hold age, required hold, available delta/threshold and temperature. It never creates a fake missing metric.
- `runtime/charge/runtime/mix_scaffold.py` and `mix_finish_hold.py`: finish-hold event records source mode, source extrema/delta/required delta, and the **actual pinned profile hold duration**; standalone default comes from canonical `mix_finish_hold_seconds()`. No additional hold timer.
- `runtime/charge/evidence/mix_progress_journal.py`: pure read-only `MIX_PROGRESS` builder. The production composition calls it only during the **existing 10-minute CHECKPOINT**. It uses RD regulation code where available and existing session-bound signal metadata. Wrong session, absent analysis, invalid or stale timestamp (bounded by existing `WATCHDOG_TIMEOUT_S`), or unknown regulator are explicitly marked unconfirmed. The existing finish-start timestamp permits elapsed-hold reporting; it does not start another clock.
- `runtime/charge/evidence/temperature_source_journal.py`: focused non-actuating read-model observer. Existing `_meta.temp_ext` source/entity/status/age and measured temperature are logged on first observation, changed source/status/session, or ≥0.5°C change (noise gate, **not** a safety threshold). Duplicates are suppressed, failed journal writes do not mark a record persisted, and failures cannot interrupt the charge/safety loop. Existing `temp_ext_v2` is not replaced by an unverified legacy fallback.
- `runtime/ui/components/journal_format.py`: human-readable Telegram formatting for MAIN minimum/reset, MIX start/progress/extrema/confirmed deltas, actual finish-hold duration, and temperature-source evidence. Historical finish-hold text is still recognized.

## Virtual dry-run and validation

Independently exercised the pre-existing **separate** `feature/dryrun-virtual-devices` worktree (D177 virtual RD6018/ESPHome/HA/Modbus, not deployed/integrated into the current branch): **31 PASS, 0 FAIL** for scenario engine, synthetic faults, lost ACK and stale sensors. This simulator is not a chemistry model and its results are not physical permission.

Current working branch focused HMI/MAIN/MIX/log regressions: **201 PASS, 0 FAIL** after temperature observer modular extraction; subsequent specific MIX checkpoint/presentation cohort **55 PASS, 0 FAIL**. Final broad re-run is tracked separately and must be confirmed by exact terminal exit code before this document claims further numbers.

## Remaining and safety boundaries

1. Physically reconcile external temperature 25°C on RD display versus 23°C in prior Telegram screenshot only with **fresh direct ESP Native** external NTC readback (registers 34/35, identity and timestamps) and secondary HA comparison. Screenshots were not simultaneous and cannot establish a calibration defect.
2. Verify installed node104 Telegram operator output, unified journal completeness, and full MAIN→MIX→finish acceptance only under a separately approved release and physical test procedure. Local tests are SOURCE PASS, not production PASS.
3. Avoid inferring CC/CV from U/I ratios, generating artificial Imin/Vmax, retrying unverified actuation, or turning uncertainty into a safety decision.
4. No new scheduler, charge engine, journal DB, second owner or automatic backup/rollback mechanism.

After final test, update both checkpoint/runbook with exact source commit SHA and whether GitHub synchronization occurred.


## Final source acceptance — 2026-11-09

- Tested code commit: `c70a6de38efbd6de8540ae09e6c3b40d4d524805` on `feature/main-mix-countdown-display` (HOME-PC). 14 scoped source/test files; temperature and MIX progress are focused read-only evidence modules, not additions to the charge algorithm.
- 26-module MAIN/MIX/HMI/journal/temperature/physical-executor dry-run regression: **212 passed, 0 failed in 102.18 s**. Compileall and `git diff --check` PASS. The validation logfile in ignored `.recipe-studio-local/rd6018_journal_validation.txt` explicitly records `FINAL_VALIDATION_PASS`, `FINAL_EXIT_CODE=0`; this was independently rechecked even though the remote execution wrapper once returned a conflicting process code.
- Separate legacy virtual-hardware worktree `feature/dryrun-virtual-devices`: **31 passed** (D177 scenario, virtual device, ACK loss, faults and recipe). It was **not merged** into the working branch. Virtual thermal limits and chemistry remain synthetic.
- The MIX-progress event is emitted **only on the pre-existing 10-minute checkpoint** while an admitted active MIX session exists; no new scheduler/clock. Source/freshness/session mismatch generates an explicitly unconfirmed event without Imin/Vmax or Delta measurements.
- The temperature-source observer uses only live input plus existing `_meta.temp_ext`/canonical freshness, with a 0.5°C journal-only duplicate gate; failure to log cannot block the charging safety loop. It does not claim correction of the physical 25°C versus prior Telegram 23°C discrepancy.
- **Installed node104 untouched.** No real ESP Native readout, live Telegram acceptance, Output/voltage/current actuation, firmware change, release activation or GitHub push. Source PASS must not be called production PASS.
- Git publication: user-owned `origin=https://github.com/timspb/rd6018_bot.git`; branch was 35 commits ahead immediately after the code commit. Documentation checkpoint commit follows; no force-push or branch reconciliation attempted.
