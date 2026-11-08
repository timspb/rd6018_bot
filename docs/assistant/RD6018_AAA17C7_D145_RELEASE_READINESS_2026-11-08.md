# RD6018 — aaa17c7: D090/D144/D145 release readiness (2026-11-08)

Status: **OFFLINE SOURCE STAGED / LIVE ADMISSION HOLD**.

## Verified source identity
- Exact tested code commit: `aaa17c744464dce44cf5839c6a81e784a21430e9`; later Git HEAD `990466494f24c60cd653b06e0c9164793f833e7b` is documentation-only and not the runtime candidate.
- Owned remote: `https://github.com/timspb/rd6018_bot.git`, branch `feature/main-mix-countdown-display`.
- Complete uninterrupted source test suite for the exact code: **3048 PASS, 3 skipped, 6 warnings, exit 0**.
- Canonical local source-only stage: `/tmp/rd6018-release-aaa17c7-20261108/release-aaa17c744464dce44cf5839c6a81e784a21430e9-in2cml6h`.
- `source.tar` size **10,219,520 bytes**, SHA256 `3e138f751d09b9008737f363517cf8a72b78bf9cdd28f62c9d3507b2c69261b9`.
- `RELEASE_MANIFEST.json` size **270,935 bytes**, SHA256 `cf23e8270fa0c1bea930ec1f107711f1cb8c4f087b2c49d0f0dfefab0d82a6f2`; `STAGED_OK` records `tree_verified=true`, manifest SHA and `directory_fsync=true`.
- Git diff from historically pinned installed slot14 source `d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b` to candidate contains **119 changed tracked paths**, none under `esphome/` or `firmware/`. This comparison is historical only; deployed source bytes need live inventory confirmation.

## Existing production mechanism — do not redesign
1. Established D090 owner + lock, D144 transition, D145 Python-only entrypoint, D148 read-only state-preserving observer. No parallel bot, new installer or new release authorities.
2. `tools/node104_atomic_deploy.py` is **only** an offline source packager/simulator; never treat its `stage` as production activation.
3. Source `tools/node104_d145_entrypoint.py` currently hard-pins **old** source `d351c208cbf8666f881a4660df6a0b211170e857`, preimage `9651e979…`, D146 profile SHA `a2610e4c…`, candidate identity `45b6ae0e…`. It is **not** an entrypoint for `aaa17c7`; never change these constants blindly or repurpose the old immutable profile.
4. D138 admission requires exact source tree, paired `RELEASE_MANIFEST.json`, verified production **Python 3.11** candidate venv, `pip check`, minimum inventory and disk capacity, installed-app preimage digest, preserved session/Guard identity and fresh physical D091 proof. The local source stage is **not** a D138-ready node104 candidate.
5. The historical D090 journal reportedly remains `STARTED`; D144 has a separate slot/journal path. Validate current journal state through the existing D090/D144 owner; never erase/forge it.
6. D145 release profile schema 2 includes exact `ReleaseManifest` fields, `preimage_inventory_sha256`, list of changed paths and reviewed collector hash. Source and preimage must come from a **single fresh observation**, not historical documentation.

## Read-only preflight evidence / open boundaries
- Read-only node104 connection was previously authenticated using existing HOME-PC connection profile: service `rd6018-bot.service` **active/running**, PID `231800`, start `2026-11-07 08:41:27 UTC`, filesystem **3.5 GB free**, 54% used.
- HOME-PC to `192.168.1.28:6053` TCP: reachable. A Telegram screenshot showed R18 OFF, U/I=0, no trip and programmed 16.50V/2.40A, but this is **not independent timestamped ESP Native proof**.
- Actual fresh ESP Native R18/voltage/current/protection/lease callback and HA comparison, active session/Guard snapshot, installed source/venv byte inventories, updated D090/D144 transaction journal, current service/user environment hashes **not yet verified**.
- A previous attempt to execute the D091/D148 observer on node104 was blocked by execution safety policy. **Do not route around that refusal with another transport or wrapper.** Production physical OFF / pre-stop admission is therefore HOLD.
- HOME-PC WSL `python3.11` absent at this inspection; no local D138-compatible venv was built. Use existing approved Python 3.11 environment where available; do not downgrade D138 interpreter checks or fabricate venv evidence.

## Next admissible sequence
1. Obtain approved direct, timestamped ESP Native observer + independent HA102 proof, and read-only installed app/venv/session/Guard/journal inventory using the already established permitted production path. If blocked, report the blockage and stop.
2. Under the **same D090 owner**, bind source-paired D145 profile to exact candidate archive, the newly observed installed-app inventory and reviewed D148 observer, with source/venv candidate identity (never reuse historical pins).
3. Stage candidate Python 3.11 venv and full source in the existing D138 location and run **prepare-only** admission. That phase must explicitly report no activation authorization.
4. Execute through the D144/D145 established owner **only after** fresh safe physical OFF/lease/Guard admission and separate explicit permission for the node104 service transition. Preserve production state and historical journals.
5. Verify post-start fresh independent Native/HA observations, single process/owner, Telegram/restore contract, and a complete journal COMMITTED. No hardware START or setpoint actuation as part of deployment.

No production writes, staging on node104, service interruption or hardware actions occurred in this offline preparation.
