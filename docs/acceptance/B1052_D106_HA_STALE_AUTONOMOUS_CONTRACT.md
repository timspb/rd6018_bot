# B1052 — D106 HA autonomous stale-but-equal secondary evidence

Status: **SOURCE-ONLY CANDIDATE; PHYSICAL P3/P8 NOT ESTABLISHED; NOT IN FROZEN B1048 ARCHIVE**.

## Real reproduced condition

B1051 directly observed canonical ESP 2.3-ha-canonical on node104, R18 OFF, measured U/I 0, R16 0, Native autonomous=false and lease fresh, with no session or recovery quarantine. HA REST R18/U/I/R16/Vset/Iset were 3.5–4.1 seconds fresh and consistent. HA binary autonomous=false had `last_reported` age **14,460s**. Installed D106 `collect_live` rejected the otherwise normal OFF reading on this one unchanged secondary HA field. HA documentation defines `last_reported` as time integration publishes an entity; ESPHome's ordinary binary sensor does not necessarily repeat unchanged states. See B1051 source record. This is NOT evidence that Native is stale.

## Narrow code change (separate B1052 worktree)

- `tools/node104_d106_live_observer.py::_ha_record`: only HA `autonomous`, when valid but older than original 8s, returns its **original** `reported_at_epoch` tagged `status=stale_advisory`. Unknown, malformed, future or nonboolean values still fail. All other HA fields use the original strict `ro._ha_freshness` and eight-second cutoff.
- `tools/node104_d106_readonly_projection.py::_field`: accepts this exact HA-only advisory tag only for `autonomous` and only if genuinely older than eight seconds. Missing/wrong provenance/type, fabricated fresh status, any other stale HA field, unsafe HA value, fresh Native wrong/stale/ON and lease or physical mismatch still reject. The actual fresh Native `BinarySensorState` autonomous remains mandatory, alongside Native R18 and measured U/I.
- D106 `source_provenance.ha102_autonomous` explicitly reports the true last HA report timestamp, tag and advisory role. No old HA timestamp is replaced with `now`, no fake callback, no new backend/client/sensor/physical operation. The shared TrialOffProof DTO and existing actuator/ExecutionPort/lease/firmware code are unchanged.
- New unit tests cover exact B1051 age, end-to-end record -> projection and all negative boundaries. Existing Native phase read-only observation remains unchanged.

## Independent validation

- HOME-PC WSL `/usr/bin/python3 -m unittest` over B1052 plus existing B1033, D091, D106, D145, D149 cohort: **137 tests PASS** (one expected in-test argparse invalid-phase stderr, outer unittest returned 0).
- `git diff --check`: PASS.
- No node104 changes, no firmware flash, Output, V/I programming, HA writes, service, node files, CI full suite or D138/D142/D145 live acceptance. The source patch exists only in branch `fix/rd6018-d106-ha-autonomous-advisory-20261127` until reviewed and published. It is NOT a physical PASS or authorization to release or replace source-paired B1048 `b016e0ad`.
- Original canonical P0–P9 remains **99/104** (three P3 and two P8 HOLD). Any revised release candidate must be freshly frozen and source-paired; never mutate existing B1048 archive.
