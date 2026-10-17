# D107 — ESP128 Native API authority over HA cached route (2026-10-18)

## Established architecture and corrected misconception

There is **one** physical ESP128. The two communication paths are
(1) ESP128 Native API direct and (2) ESP128 via Home Assistant REST.
Those are neither two independent hardware sensors nor two separate physical
controllers. **Native API is the preferred/authoritative evidence source.**
HA is an optional secondary transport and diagnostic cache and must not
overrule fresh identified native callbacks merely because HA `last_reported`
is old or unavailable.

This explicitly corrects the D106 assumption of two equally authoritative,
independent physical sources. No HA-only snapshot qualifies for a
D090 release or D104 OFF-only physical trial; the HA fallback path for ordinary
read/control is a different runtime transport policy and must retain
its own constraints. D090 never fabricates healthy zero values when HA is absent.

## Confirmed read-only observation on node104

One pinned-host-key diagnostic on 2026-10-17 showed HA
`binary_sensor.rd6018_rd_6018_safety_autonomous_mode` = OFF, but its
`last_reported` was 20,063.5 seconds old (~5 h 34 min).
At the same observation Native API callback values were:
`safety_autonomous_mode=false`, `safety_lease_armed=false`,
`safety_lease_remaining=0`, `safety_lease_ttl=900`,
`safety_modbus_age≈1.75s` with callback cache ages ~0.5 seconds.
One production bot MainPID=69648, restarts=0, no D090 journal, no drop-ins.
This was observational only; no physical command, systemd mutation or release.

## Source-only changes

- D106 projection: full typed, fresh native evidence compulsory; HA advisory
  does not veto. HA unconfigured/stale/unavailable/contradictory leaves the
  native proof intact. Unsafe/stale/missing native fails closed.
- D106 adapter: concurrent best-effort HA reads, explicit HA health diagnostics;
  authoritative native edge state only.
- D091 physical proof: same priority; HA fields `None` when absent/stale;
  never fabricate HA OFF. Full native R18/voltage/current and all edge
  containment flags retain their type/freshness/safety gates.
- D090 release validator: native OFF, 0 V/0 A, fresh source, device/owner and
  lease containment remain required. HA advisory must be fully typed when
  present; may be absent or differ without veto.
- D090 transaction baseline: no HA cache state in the immutable owner/containment
  fingerprint; unstable HA presentation cannot trigger a spurious abort.

## Configuration consistency

`config/physical/connectors.yaml` already selected `esp_direct` at priority 10 over `ha_esp` priority 20, but `config/physical/transports.yaml` still declared default `ha102` with reversed priorities. Corrected this declaration to default `esp128`, priority 10, and HA102 priority 20. The current loader selects the active physical connector from `connectors.yaml`; it does not consume the `default_transport` declaration as an active path, so this is a source-only consistency and future-proofing correction, not a production switch.

## Fresh node104 OFF-only read-only preflight

A second exact-pinned SSH identity check and a short-lived read-only
diagnostic (Windows operator file
`E:\\CODEX\\RD6018_D107_NATIVE_FULL_READONLY_20261018.py`;
**not** installed on node104) used the deployed D091 native read helper,
fresh SensorState callback subscriptions and native BinarySensorState
cache. HA was not used for physical admission.

Observed firmware identity matched
`timspb.rd6018-pb-recovery-v2 / 2.2-autonomous-authority`.
One native device identity, one production bot process, PID `69648`,
`NRestarts=0`; no systemd drop-in or D090 transaction journal.
Native R18=0, V/I=0/0, R16=0, autonomous=false,
lease armed=false, remaining=0, TTL=900,
native Modbus age≈5.89s (within 20s), lease trip=false,
boot quarantine=false; readbacks Vset/Iset=13.57/0.10,
OVP/OCP=14.07/0.20. No active charge session or quarantine.

The installed 8b75 source has `safety_lease_ttl` SensorInfo but
lacks `edge_lease_ttl` in its older edge_entities map. The D107
source-only observer uses precisely the reviewed D091 pinned native
`safety_lease_ttl` identity for this one missing key, checking a
fresh typed native callback. It does not invent a value or use HA.

A fresh independently calculated D090 inventory of installed
`/opt/services/rd6018-bot/app` produced **1,584 filesystem objects**;
SHA256 of canonical sorted JSON inventory was
`ef24cf5a66abe0991e4e5ceb04988c25806ee9a74d9025ebde00bf3161919171`
(**MATCH**); root `.env` digest
`3ca2c77f25c0cde39d5c405114220dc6135197e1f68f3371e9ba8b7ff473a185`
(**MATCH**) and exact systemd unit digest
`74146a925d8c80a6a240f78877e76e060e674f6928f748db43891e7ff1b0e068`
(**MATCH**); machine ID and marker
`8b75cca153f00847d84396aba392472bb7552ad4` matched the pinned
production identity. No Output operation, lease operation, systemd
mutation, file install or physical D097 Enter/Exit was issued.

**Boundary:** This is a native read-only preflight using a diagnostic,
NOT installation or full end-to-end acceptance of the new D106 observer
and not the D090-managed crash/journal/socket physical trial.

## Runtime transport selection

`HassClient.from_physical_config()` constructs one selected backend
from `default_connector=esp_direct`. Existing `ha_esp` is a separately
available path, not an automatic runtime fallback. On native errors,
the current code does NOT automatically hand off read/write operations
to HA. A future runtime fallback must preserve single-owner physical
commands and must never continue a partially executed write transaction
under another backend without explicit recovery/verification.

## Verification and boundaries

Regression matrix verified in isolated WSL2 Ubuntu-24.04 worktree at
commit `de97dff52644ab750df44ca0da82856cb4eaab15` against the installed
project Python 3.12.3 virtual environment:
- Focused D090 release/transaction, D091 collector, D106 projection and
  live typed-SensorState adapter, native-first config, strict measured provenance and legacy firmware TTL mapping: **80/80 PASS**.
- Initial 76/77 run detected `set_current_a=0.8 > ocp_a=0.2` incorrectly
  accepted by `TrialOffProof.validate`. Fixed in D090 common validator;
  the focused suite passed 77/77; after adding direct/native config\n  precedence regression and correcting `transports.yaml`, it passed **78/78**; additional provenance and legacy TTL\n  compatibility regressions increased the focused result to **80/80**.
- WSL2 `compileall -q` on tools/tests PASS; `git diff --check` PASS.
- Full test-suite execution was attempted but blocked by the execution tool;
  **NO full-suite or GitHub CI PASS is claimed on this branch**.
- Creation of a GitHub PR was separately denied by the tool; do not claim
  a PR exists or bypass the refused operation.

Negative regressions cover stale/unavailable/unknown/disagreeing/malformed HA,
unsafe native, wrong callback class/source, native TTL !=900, stale Modbus,
broken source IDs, SensorState/NumberState object-id aliasing, setpoint versus
OCP, and toggling HA availability during offline D090 baseline verification.

**Still OPEN**: production live D106 observer end-to-end on node104, independent
OFF/lease proof accepted at each trial edge, exact temporary root-only socket
and drop-in rollback, all trial crash/journal boundaries and D097 Enter/Exit.
No automatic production deployment or physical trial is authorized by this
source-only correction.
