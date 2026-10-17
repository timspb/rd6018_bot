# D091 — node104 live ESP managed evidence collector (2026-10-17)

## Scope and result

D091 adds a standalone JSON-only, read-only node-local collector for the strict
`node104_d090_release.PhysicalOffProof` schema. It is intended to be copied later
to `/opt/services/rd6018-bot/d090/` only after its digest is reviewed and pinned
in D090. This work does not install or run it on node104 and does not authorize a
D090 transaction.

The collector uses `runtime.config.load_config`, HA102 REST state reads, and the
legacy deployed ESPHome transport's `discover`, native subscription and state
metadata. It explicitly loads the deployed config
root `/opt/services/rd6018-bot/app/config`. For edge entities absent from the old
configured read whitelist, it reads only the existing native subscription cache
(`_state_cache`, `_state_types`, `_state_updated_at`) for unambiguous edge
entities and requires native callbacks no older than eight seconds. For measured
R18, voltage and current it validates `SensorInfo` inventory entries and captures
new `SensorState` payloads from the passive subscription, keyed by native entity
key and timestamped at callback time. The voltage/current IDs can also have
`NumberInfo` setpoint entities and `NumberState` callbacks (for example 13.57 V
and 0.10 A); these programmable setpoints never count as physical output
measurements, and their shared object-ID cache timestamp cannot refresh measured
sensor freshness. The collector waits up to ten seconds for all three fresh
typed measurement callbacks, then performs HA REST reads so their
`last_reported` timestamps are current. Missing, stale, or wrong-type callbacks
fail closed. It does not rely on newer
`get_physical_output_report`. Independent HA numeric R18 plus HA `last_reported`
and attributes, native ESP `SensorState` R18 plus callback age, numerical finite
V/I, edge lease/boot/trip/autonomous/conflict/intrinsic-fault state, the exact
900-second TTL, persisted session/journal documents, systemd MainPID/process
identity, host machine ID, ESPHome device identity, and distinct per-read nonces
are checked fail-closed. Output values must be strict numeric zero; Python
booleans do not qualify.

Pure `assemble_proof` and persisted-document validators are independently
testable against fake snapshots. Live collection only makes read requests and
closes both transport clients in a `finally` block. Failures are emitted on
stderr with nonzero exit; stdout is exactly one JSON proof line on success and
contains no credentials.

## Independent live observation recorded before D091

The installed node104 application is old source `8b75cca153f00847d84396aba392472bb7552ad4`,
with bot PID `59725`. Its native ESPHome firmware reports version
`2.2-autonomous-authority`, compiled `2026-10-11 22:40:30 +1000` on ESPHome
2026.8.2, device name `rd6018-controller`, model `esp01_1m`. The old API's
`device_info()` has no `device_id`; native entity inventory reports the single
physical ID `0`. The collector matches project/version/name/model and configured
ESP host independently, then requires exactly one native inventory device ID.
Independent read-only current evidence reported native R18 OFF, 0 V,
0 A, battery 13.06 V, edge lease disarmed, trip clear, generation 55, TTL 900 s,
autonomous false, authority conflict false, intrinsic fault false, and no
persisted charge session or quarantine journal. These are recorded observations,
not evidence collected by the new D091 source and not a D090 post-stop proof.

## Physical acceptance remains open

The node's installed firmware identity corrects prior documentation that could
be read as saying the pre-D065 image remained installed. It does not establish
that D065 passed. Network outage beyond 900 seconds while energized, ESP reboot
with Output ON, raw protection injection, and thermal injection remain OPEN.
The D065 bench gates and other D061-D065 exact-source acceptance requirements
in `esphome/README.md` remain controlling. The source correction establishes
compatibility with the installed API shape; live collection was subsequently demonstrated on node104 for a pre-stop
proof only; it does not establish a post-stop proof or D065 physical acceptance. No AGM/MIX/MAIN or 900-second lease
behavior was changed by D091.

No hardware writes, Output ON, live bot stop/restart/deploy, OTA, firmware,
service-manager mutation, or GitHub push/merge was performed for this change.

## Fresh D091 live pre-stop collector acceptance — PASS (2026-10-17)

After multiple strict fail-closed compatibility diagnostics on the installed
Python3.11/ESPHome API, the exact D091 source was executed **in memory**
through the existing SHA256 host-key-pinned/known_hosts-confirmed node104 SSH
connection. The script was neither installed nor persisted on node104.
Read-only release-proof fields returned exit=0 and one JSON object:

- Source SHA256: `c6bf8f456c06da75816976946a9129ccd7619237b6e482874c25a4aa9951ace8`.
  This applies to the tested source at the time of the live probe and must
  be recomputed if it changes.
- `captured_at_epoch=1792225700.8071115`; pinned machine ID matched;
  service `MainPID=59725` (thus **pre-stop**, NOT a post-stop proof).
- HA102 numeric R18=OFF, V=0.00 V, I=0.00 A with fresh REST source timestamps.
- ESP128 *new typed SensorState callbacks* gave R18=OFF, measured V=0.00 V
  and I=0.00 A; the simultaneous programmable `NumberState` setpoints
  13.57 V / 0.10 A were explicitly rejected as physical measurements.
- Edge armed=false, boot quarantine=false, autonomous/conflict/intrinsic-fault
  flags false, lease TTL=900 s; no active persisted session/quarantine incident.
- Physical entity identity count=1, distinct source challenges, collector
  emitted no secrets and sent no RD6018 or ESPHome commands.

Evidence boundary: this is a positive **read-only pre-stop D090-compatible
collector sample**. It does not prove behavior after service stop, automatic
rollback, exact-source D061-D065 powered acceptance, or successful deployment.
The older installed bot was not restarted and the external observer was not
changed. No charger Output ON was requested.

The reviewed read-only collector SHA-256 above is now pinned by the
D090 transaction runner. This removes the **source-integrity** gap for
the collector without installing it on node104 or authorizing activation.
The still-missing physical D065 acceptance signature/firmware digest,
fresh post-stop proof, and controlled production deployment remain OPEN.
