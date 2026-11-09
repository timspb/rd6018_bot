# RD6018 — f16cd30 offline release readiness, 2026-11-10

## Scope and exact source

- Local owner repo: `E:\CODEX\rd6018_bot`; owned origin `https://github.com/timspb/rd6018_bot.git`.
- Tested candidate source SHA: **`f16cd30c40200e26c0dd736737f4cbdb61f9885e`** on `feature/main-mix-countdown-display`. Relative to historically installed D144 slot16 code `3f50133b0dca9d274a08d4dd7999f730ce90e962`: **69 tracked paths changed**. This is NOT a two-file hotfix: dependent modules, recipe Studio, HMI, MAIN/MIX, Guard, safety, tests and docs are part of the candidate.
- The most recent verified LIVE optional ESP read-only observation (2026-11-09 14:50:46 UTC) identified actual firmware `2.3-ha-canonical`, fresh R18=0/OFF and typed Native callbacks: `control_output=False`, `take_ok=True`, `take_out=False`, `boot_power=False`. This was a read-only diagnostic at that instant, **not** preinstall physical admission.
- `e99d434` fixes the Native transport value + metadata resolution for SwitchInfo/BinarySensorInfo, source and direct real-device evidence consistent. `f464931` + `6453ea6` fix the prior EFB MIX → SAFE_WAIT → Storage journal/persistence/owner mismatch and immediately contain post-enable commit failures via existing ExecutionPort. Production Storage repair is not yet accepted physically.
- `f16cd30` updates the historical D123 test for the intentionally new `MIX_STARTED` event, without runtime changes. Prior complete checkout suite ran **3185 PASS, 1 FAIL, 3 skipped** only because that legacy test still asserted `START | V2_MIX`. Focused 23-test main/transition/journal cohort passed after the expectation correction.

## Exact immutable source-only package

Existing, unmodified `tools/node104_atomic_deploy.py stage` generated a local Git-archived source candidate (no SSH, systemd, node104 filesystem writes or actuator actions):
- Stage directory: `/tmp/rd6018-release-f16cd30-20261110/release-f16cd30c40200e26c0dd736737f4cbdb61f9885e-5uzn2k04`.
- `source.tar`: **10,926,080 bytes**, SHA-256 **`7bed2d7986b41ab75e8e04b222c90141bd0d7fa30eed86344bb53993ba79f5b1`**.
- `RELEASE_MANIFEST.json`: SHA-256 **`b0558afab6dc56039ea226fb1b2d90c80af2721442b9ba14fa7840ce4f5aaeb3`**.
- Manifest includes **1462** regular source files. Verified every extracted file hash/mode/size and exact file set, source archive digest, marker manifest digest, `tree_verified=true`, `directory_fsync=true`. Read-only re-verification returned `OFFLINE_STAGE_VERIFIED`.
- Candidate has **no** bundled production `.env`, state directory, SQLite database, live user recipes, venv, Telegram token or lease material.

## Testing

- Proper canonical production regression collection: `PYTHONPATH=tools:.:tests PYTHONDONTWRITEBYTECODE=1 /home/home-pc/.venvs/pcp-test/bin/python -m pytest -q -p no:cacheprovider tests`. **Final exact-SHA full suite: 3186 passed, 3 skipped, 10 warnings, 0 failures, exit 0 in 489.73 seconds** (8:09), log in ignored `.recipe-studio-local/rd6018_full_suite_f16cd30.txt`. The earlier retired `START | V2_MIX` test mismatch was corrected at `f16cd30` and its focused 23-test cohort passed before this full rerun. No new charging algorithm change.
- An unscoped `pytest` invocation additionally discovers retired `tools/acceptance_guard/test_sinks.py`; it fails **collection** because historical `managed_runtime_safety` no longer exists as a top-level module. That suite targets D061 supplemental source SHA `594a386...` per its own README, not the current canonical runtime; do not add a compatibility shim or mistake collection error for a charging regression.
- Regression must pass as a whole for the **exact source SHA** before a production release profile is considered.

## Production admission HOLD

1. The existing actual versioned D090/D144/D145 transaction owner must receive its own newly reviewed **source+venv+preimage D145 profile**. Existing `tools/node104_d145_entrypoint.py` pins older source `d351c208...`, preimage `9651e979...` and candidate identity `45b6ae0e...`. Never reuse or silently rewrite these pins for this candidate.
2. From node104 collect **fresh, comprehensive direct ESP Native** physical status including R18, measured U/I, Vset/Iset, protection R16 and OVP/OCP, battery voltage, the 900-second lease/Modbus freshness, session/Guard/ownership identity; independently compare HA102 secondarily. The earlier isolated R18 read is historical and insufficient for a new deployment.
3. Obtain the newly observed installed app/venv/backup/journal and `state/` inventories and disk/free-space preimage. D144 slot16 deployment is historical; the actual present node104 SHA and D090/D144 journals must be read-only checked. Preserve recovery quarantine and past transactions. Do **not** reset active EFB SAFE_WAIT or erase session to satisfy install gates.
4. Use the existing protected Python 3.11 staged candidate/venv and D138 prepare-only path; source packager is **not** D145. Explicitly require separate authorization for service stop/install/restart. No hardware START or setpoint/Output writes as deploy smoke.
5. After separately authorized install, test the four optional Native statuses through normal newly deployed `get_live_values`, check R18 independently, and verify Telegram operator journal and session recovery. Full EFB MAIN→MIX→SAFE_WAIT→Storage physical activation is a **separate** supervised acceptance, not inferred from tests.

**Disposition: SOURCE ARCHIVE VERIFIED; node104 installation and hardware acceptance HOLD.** No production filesystem, ESP, HA, Output, lease, voltage/current or firmware commands were sent in this stage.


## 2026-11-09 15:22:26 UTC — fresh node104 metadata (read-only, not physical preflight)

Existing HOME-PC pinned SSH profile (host key verified, credentials not printed) was used only for `systemctl show/is-active` and a read-only parsed session/control-mode query. No service stop/restart or ESP/HA read/write in this metadata stage.

- node104 host `rd6018-bot`, `rd6018-bot.service=active`, PID **237957**, `NRestarts=0`, service start **2026-11-08 15:20:03 UTC**.
- Durable `state/charge_session.json` had `stage="Безопасное ожидание"`, `safe_wait_next_stage="Done"`, `completion_kind=null`, `output_intent=null`, and **MAIN Guard present**.
- Durable `state/rd_control_mode_v2.json`: **`pb_managed`**.
- This query did **not** locate a deployment marker in the three guessed paths and did **not** inventory the active app or D090/D144 journal. It cannot establish the exact installed code SHA independently; D144 slot16 code identity remains a historically reported release. A currently retained SAFE_WAIT session is an explicit release admission constraint; no implicit Storage resume, state deletion, artificial terminal intent, or physical enable is permitted.
- The earlier **2026-11-09 14:50:46 UTC** ESP Native direct read (firmware identity, optional typed status callbacks and R18 OFF) is a separate prior observation, **not** a simultaneous physical preflight at 15:22.

## Readiness verdict

**SOURCE FULL-SUITE PASS / OFFLINE SOURCE ARCHIVE VERIFIED; D138/D145 NODE104 PREPARE+ACTIVATE HOLD**. The candidate cannot be treated as a safe hotfix until active protected session, fresh exact app-preimage inventory and physical OFF/lease evidence are reconciled by the existing owner. No production mutations made.
