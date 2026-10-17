# D105 — D090 schema-2 bench-trial transaction, software acceptance only

Date: 2026-10-18.

## Objective and current result

**D105 OFFLINE TRIAL ENGINEERING PASS. Production trial and D097 physical
Enter/Exit remain OPEN.** Do not mistake offline rollback tests for a
completed bench trial or a production deployment.

The existing `tools/node104_d090_transaction.py` remains the **only owner** of
installation, service stop/start, journal and rollback. D105 does not introduce
a second installation service, Telegram process, hardware actuator or release
CLI.

## Source bundle: reviewed D103 source and deterministic D105 stage

- Reviewed D103 source commit:
  `b3cd0174a2918dbbc2ee3f9c908fa14d15089a29`.
- Original D103 `SOURCE_MANIFEST.json` SHA-256:
  `665a12dbd6f216740be182a61c5a842419d4cbf7c4ab0b40abcb4cb2ef94c17f`.
- Exact reviewed D103 `source.tar` SHA-256:
  `410af38f6a8ec059560aa1bc351b00a572a96121c3d93a216cbe86a433e84ae4`.
- `tools/node104_d105_stage_trial.py` transforms the exact source-only
  archive, without modifying source bytes, into a D102-compatible review stage.
  It rejects wrong source SHA/digest, traversals, duplicate paths, symlinks,
  unsupported tar member types and inventory mismatches.
- D105 `RELEASE_MANIFEST.json` SHA-256:
  `f9c5725638b77a6e76e52cb7269b2e95f1fdbeda8b442d6c6b9811e347947575`.
- Complete source inventory: **1027/1027 source files SHA-256 verified** by
  the canonical D102 validator after extraction.
- HOME-PC stage:
  `E:\CODEX\RD6018_D105_REVIEW_STAGE_b3cd0174a291`.
- The stage includes `STAGED_OK`, but that is only source-integrity evidence.
  It **does not** authorize a node104 install, trial, or bypass of physical gates.

## Lifecycle implemented inside D090

D105 adds reviewed `TRIAL_SOURCE_SHA`/`TRIAL_PIN`, typed `TrialOffProof`,
and methods `D090Transaction.begin_trial()` and `finish_trial()`.
`recover()` dispatches schema-2 trial journals back to the same owner.
D090's original schema-1 production release pins and acceptance rules remain
unchanged.

- Trial journal: schema `2`, purpose `D104_OFF_ONLY_BENCH_TRIAL`, unique
  transaction identity, baseline hashes, source/manifest SHA, exact candidate
  inventory, independent programmed-setpoint baseline and durable backup digest.
- Trial phases are `PREPARED → STOPPED → BACKUP_DURABLE → rename stages →
  TRIAL_RUNNING` and always conclude with `TRIAL_RESTORED`, not `COMMITTED`.
- Stop/swap/restore occur only under D090's existing `flock`. The preimage
  app, venv, state, environment, unit and marker are checked, backed up,
  durably flushed and restored. No charging session is allowed during the trial.
- Before transitions, fresh independent `PhysicalOffProof` must still verify
  HA/native OFF and measured zero V/I. A separate typed D105 edge readback
  requires `AUTONOMOUS=false`, `lease_armed=false`, remaining 0, configured
  TTL 900 s, raw R16 Protection=0, Modbus age ≤20 s, programmed voltage ≤15.5 V,
  unmodified V/I/OVP/OCP and unique fresh challenge. This prevents trial
  shutdown or restoration during an energized/ambiguous authority state.
- Every simulated fault around journal, app/venv rename, startup and restore
  must either restore exact old source or stay contained without blind restart.
  A crash **after partial backup creation but before durable BACKUP_DURABLE journal**
  is recovered from the independently verified unchanged live preimage; the
  unsealed backup is explicitly marked ignored and retained only for inspection,
  never accepted as rollback evidence.
  Corrupt backup, tampered source/preimage, stale evidence, unsafe autonomous
  state and changed setpoints cause explicit rejection.
- `trial_socket_ready` is required to prove the *production coordinator*
  physical-test socket; it is not a substitute actuator or second listener.

## Intentionally unimplemented production bridge

**Production D104 activation is disabled in this release**:
`_trial_gate()` requires an offline fake adapter and rejects
`SystemdService` or the production root. Neither `begin_trial` nor
`finish_trial` is exposed as an executable production CLI subcommand.
There is no D104 live edge-proof provider or approved managed, temporary
systemd AF_UNIX socket lifecycle yet. Therefore the software state machine
cannot be mistaken for a permission to switch the running bot.

D090 schema-1 `prepare|activate|recover` and its source/signature/firmware
gates remain untouched. The node104 service's installed
`8b75cca153f00847d84396aba392472bb7552ad4` is still the last observed
production source; no new node readback has been performed in this sprint.

Before any genuine D097: review a **single-owner node-local adaptor** for
independent actual HA102/native ESP128 typed state, the temporary production
AF_UNIX socket and its safe cleanup, pre/post-stop physical proof freshness,
complete 1:1 preimage restoration, live journaling and bounded operator
supervision. Production trial must be treated as a separate reviewed execution
stage, not unlocked by changing `offline` or rewriting D090 pins.

## Software evidence

- Focused D090/D102/D105 test matrix: **57/57 PASS**.
- Real reviewed D103 archive conversion and D102 1027-file source verification:
  **PASS**.
- Full WSL suite using the existing project Python 3.12 venv: **2170 tests OK, 2 skipped**; log `E:\CODEX\RD6018_D105_FULL_SUITE_FINAL_20261018.log`.
- D105 source-stage converter negative tests and D090/D102/D105 focused tests: **57/57 PASS**.
- The GitHub CI matrix remains a separate integration check before merge.

Physical D097 Enter/Exit, D065 energized outage/reboot/fault injection,
full exact-firmware signed acceptance and production D090 release remain OPEN.
