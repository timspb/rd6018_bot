# D101 — exact-source review stage and live production pre-image audit
Date: 2026-10-17.

## Decision: backup pre-image READY; new-source D090 activation NOT AUTHORIZED
D101 independently checked exact installed runtime bytes and constructed a reproducible
candidate review stage. No application, firmware, service, actuator or release trust pin
was changed. The original D090 executable intentionally rejected the new stage.

## Production pre-image (actual node104, pinned SSH, read-only)
- Installed app .deploy_sha: `8b75cca153f00847d84396aba392472bb7552ad4`.
- Full application inventory SHA-256 observed:
  `ef24cf5a66abe0991e4e5ceb04988c25806ee9a74d9025ebde00bf3161919171`;
  **exact match** to D090 pre-image inventory pin.
- Unit SHA-256 observed:
  `74146a925d8c80a6a240f78877e76e060e674f6928f748db43891e7ff1b0e068`;
  exact match to D090 unit pin.
- Service `.env` SHA-256 observed:
  `3ca2c77f25c0cde39d5c405114220dc6135197e1f68f3371e9ba8b7ff473a185`;
  exact match to D090 environment pin. **No secret values printed or copied.**
- `app`, `venv`, `state`, `backups` are ordinary directories on one filesystem.
- Space free: **4,964,098,048 bytes** (~4.96 GB).
- No D090 transaction journal exists.
- Service `active`, MainPID **69648**, `NRestarts=0`, no systemd drop-ins.
- Fresh D091 HA/native preflight: physical Output OFF 0.00 V/0.00 A,
  managed lease unarmed, autonomous false, TTL 900 seconds.
- Raw audit saved at HOME-PC:
  `E:\CODEX\RD6018_D101_NODE104_RELEASE_GATES_20261017.json`,
  SHA-256 `039673d3d80c5977cde05e38da2628b88fa8a1d6d21e119b563926c88dcdb922`.

## Old-source D090 transaction offline rehearsal
- `python3 -m unittest tests.test_node104_d090_transaction tests.test_node104_d090_release -q`
  **17/17 PASS** (source checkout `b2388cb`).
- Exercises simulated stop/commit, backup integrity, crash boundary recovery,
  old-app restore, source pin rejection, stale physical proof rejection,
  concurrent transaction gate, and tampered candidate containment.
- Offline mocks **do not prove** a live source swap/rollback or authorize one.
- Test log: `E:\CODEX\RD6018_D101_D090_TRANSACTION_TEST_20261017.log`.

## New-source stage ready for review (not for activation)
- Source commit **b44476bcd19dbf0f4ac955634f02a4a7f9e51ddc**.
  Subsequent `b2388cb` only merges D100 documentation.
- Review directory on HOME-PC:
  `E:\CODEX\RD6018_D101_REVIEW_STAGE_b44476bcd19d`.
- `source.tar`: **1022 files**, SHA-256
  `89bb7a891c590fcd72eeb14fedd6e8405690528b627ff9ce56b91a7a91781294`.
- `RELEASE_MANIFEST.json` SHA-256
  `bebb447abf423ab3295866d95990fd2b575164dd716555f69201f9403d7e5c76`.
- `STAGED_OK` records internally verified source integrity, **not** physical acceptance.
- `README_NOT_DEPLOYABLE.txt` explicitly preserves all release gates.
- Old `node104_d090_release.verify_staged_release()` refused this new-source stage
  with expected `staged manifest digest differs from D090 pin`.

## Remaining strict admission boundaries
- D090 pins `d29db790bf7140932bc005bddf6bd5988041bfc0`;
  this is **not** the full reviewed b44476b release.
- Full accepted exact ESPHome firmware digest and reviewed physical signer key
  fingerprint are still absent.
- D097 real production coordinator Enter/Exit after deployment of the coherent
  source, and remaining D064/D065 physical fault, outage, reboot, persistence
  and managed-expiry proofs remain OPEN.
- The controlled release needs a separately reviewed **bench** acceptance stage
  and trust-root registration; no new live deployment owner should be created
  to sidestep D090's restrictions.
- Current production stays at old installed source and Output OFF.

**Engineering status:** exact pre-image and rollback transaction software are
supported by evidence; **activation is BLOCKED by intentional physical
acceptance and source-signing gates**, not by lack of admin authorization.
