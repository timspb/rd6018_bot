# B1027 — Native programmed Vset/Iset evidence readiness

Run: `rd6018-b1027-20261126-r73-native-setpoint-proof`
Branch: `codex/rd6018-b1027-native-setpoint-proof-20261126`
Base/code HEAD at start: `170aa91a7e7d8bc578f5dfa32d7fea12f411f9fa`
Result: **OFFLINE SOURCE VALIDATOR READY; LIVE P3 GATE 2 BLOCKED / NOT RUN**

## Outcome

Inspected the requested P0–P9 checklist, handoff canon, master plan, project
runbook, checkpoint, ESP Native evidence authority, B1020 physical matrix,
B1024 Native evidence helper/report, B1025 parity report, B16 readback
implementation/runbook, ESP128 config and observer, ESPHome register map,
START preflight, and output policy. Canonical status at task start is 98/103;
three P3 and two P8 physical/release conditions remain HOLD.

The direct ESP128 subscription has a separate read-only `SensorState` mapping
for Vset/Iset (holding registers 8/9). A call to the existing per-entity
`get_entity_state()` can expose source, object ID/key, device ID, Native
connection generation, callback monotonic timestamp and age. The bulk
`get_live_values()` surface projects these same readback sensors but omits
object ID and connection generation from its aggregate metadata. The normal
production transport profile is HA102; its setpoint setters return booleans.
`ExecutionPort` also consumes boolean setter results and later compares an
aggregate readback. There is no actual V/I write receipt with terminal
completion time/generation available to link to a post-write Native callback.

The B16 check remains distinct: it validates advancing `last_reported` for its
configured readback keys in the HA-shaped live view. It does not establish
direct Native provenance or post-write Native causality. No B1026 Output ON
route behavior was changed or relied upon.

Added `tools/b1027_native_setpoint_evidence.py`, an offline validator requiring
an externally captured real write receipt, the two configured Native
read-only sensor records, same ESP/generation, timestamps after both write
completion and pre-write callback baselines, <=8-second freshness, matching
setpoint values, and supplied existing policy ranges/tolerances. It neither
creates a receipt nor connects to or commands a device. Six deterministic
tests cover valid evidence, stale/HA-only/wrong type, object identity, device
and generation mismatch, pre-write/unchanged heartbeat, impossible values,
and absent receipt completion time.

OVP/OCP remain excluded from this validator and from automatic policy. No
OVP/OCP reads or writes are prerequisites; the helper compares programmed
Vset/Iset only and makes no claim about measured output voltage/current.

## Changed paths

- `tools/b1027_native_setpoint_evidence.py` — offline-only evidence validator.
- `tests/test_b1027_native_setpoint_evidence.py` — six deterministic cases.
- `docs/acceptance/B1027_VI_NATIVE_PROGRAMMED_READBACK.md` — focused evidence
  and operating boundary.
- `B1027_REPORT.md` — this report.

No production Python, ESPHome, configuration, ExecutionPort, HA, hardware,
service, setpoint, Output, lease, or checkpoint/master/handoff/runbook files
were changed.

## Verification

- `/home/home-pc/.venvs/pcp-test/bin/python -m unittest -v
  tests.test_b1027_native_setpoint_evidence` with project import path and inert
  local token: **6/6 PASS**.
- `py_compile` for the helper and focused test: **PASS**.
- `git diff --check`: **PASS**.
- No full suite, CI, ESPHome build, live observer, HA/ESP/native connection,
  physical test, deployment, node104 query, network/GitHub, staging, commit,
  push, or original dirty E-drive worktree action was performed.

## Limits and disposition

The offline validator is source readiness only. Since the current authorized
V/I setter returns a boolean and no accepted route supplies its real monotonic
completion time and generation, do not populate a fabricated receipt. Direct
Native callbacks have not been collected after a write. P3 Gate 2 therefore
remains **BLOCKED / NOT RUN**, and P3/P8 remain **HOLD**. No canonical checkbox
is closed. The existing Wake R7.3 launcher owns completion delivery; no
completion hook was invoked manually.
