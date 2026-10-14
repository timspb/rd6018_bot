# D061 negative matrix engineering gate — 2026-10-14

## Scope and decision

This checkout is based on `origin/main` at
`e79d2596dae068a7f257eb1406015fcbfe7b0c99`, on
`fix/d061-negative-matrix-runner-20261014`. This record is software/design
work only. No node connection, socket fault activation, electrical command,
OTA, production service operation, or hardware PASS was performed.

The two existing in-process hooks are present:

- `d061_fault_toctou_precommand`
- `d061_fault_ambiguous_edge_ack`

They are not yet selectable in the supervised Windows runner. `tools/run_d061_takeover_smoke.py`
accepts only `d061_fault_raw_protection_unavailable`, and its host-side
overlay validates fixed hashes for all six supplemental modules. In
particular, `tools/acceptance_guard/takeover.py` is pinned at
`2a8eb1ac9062d88d62ff0d4a247c5b71af2f31fbf6c65212fb8b6b2d3dfeb889`.
The current exact-source candidate is separately fixed at
`594a386e2b9fdd6bde9ebb15a5dfab30155291d6` with the 875-file manifest hash
`8e31b6d11c1fa2c9acbf038cd79e4f0adee7c011f8026656987c8891651ca288`.

Changing the pinned takeover bytes without a distinct reviewed candidate
attestation makes the existing overlay test reject staging. The acceptance
launcher also requires a clean checkout at its pinned candidate SHA. Therefore
the negative runner cannot be safely delivered as an executable change in
this sprint without establishing and reviewing a separate candidate/overlay
attestation and updating the launcher to select it explicitly. The existing
positive and synthetic raw-protection pins remain unchanged. The runner must
continue to fail closed until that intentional repin is reviewed; do not copy
unattested working-tree bytes into the accepted overlay.

## Required candidate behavior

The TOCTOU scenario must execute after safe enable and HANDS_OFF release, but
before `d061_adopt_battery`. Its exact typed result must prove deterministic
rejection, `command_may_have_executed=false`, equal integer generations,
external Output ON, and `hardware_writes_injected=0`. That ON is an intentional
negative-test condition and can never be a final PASS. Containment must call
the canonical guarded fault-OFF API directly, without relying on an adopted
Manual owner or using ordinary typed stop. PASS then requires fresh independent
HA and native ESP Output OFF plus zero V/A, verified lease disarm, safe
HANDS_OFF ownership, stopped acceptance composition, and restored sole
production owner.

The ambiguous-ACK scenario must call the real edge adoption command and hide
only the invoking task's positive ACK samples. Its response must prove
`contained=true`, `command_may_have_executed=true`, Output OFF, a valid
integer generation strictly advanced from the pre-command value, and final
lease/status generation agreement with the lease disarmed. The runner must
reject a malformed, mismatched, late, stale, or unknown ACK/source/generation,
and any missing independent OFF, zero V/A, authority retirement, poller stop,
or production restoration proof.

Both modes must preserve one-shot task-local injection: background work cannot
consume or inherit it. A pre-command rejection must not be reported as PASS
merely because it leaves the external Output ON. If any failure occurs after
production stop, evidence must be retained and production restart must remain
blocked until independent OFF, lease, ownership, and acceptance-poller safety
are all proven. Keep root-owned global `0600` flock ownership through restore,
isolated HANDS_OFF bootstrap before composition, 12-second fresh-report dwell,
and the lease/release ordering unchanged. Keep target values at 13.57 V,
0.10 A, OVP 14.07 V, OCP 0.20 A; the intrinsic PSU limit is 55 C and battery
probe remains separate. Do not introduce raw Modbus/HA/ESP writes or mutate
real report timestamps.

## Physical matrix boundary

| Scenario | Current evidence / next gate |
|---|---|
| Positive D061 adoption | Previously accepted physical evidence; do not repeat |
| 900 s lease endurance | Previously accepted physical evidence; do not repeat |
| Synthetic in-memory raw-protection evidence unavailable | Physical PASS documented in the 2026-10-14 evidence; do not repeat |
| TOCTOU pre-command rejection | Existing typed hook only; supervised runner candidate and offline negative-matrix tests remain open, then separate physical review |
| Ambiguous edge ACK | Existing typed hook only; supervised runner candidate and offline negative-matrix tests remain open, then separate physical review |
| Real OVP/OCP/OPP trip | HOLD until a safely isolated electronic-load/non-battery fixture and separately reviewed procedure exist |
| Out-of-band V/I/OVP/OCP upward mutation | Requires separately approved safety-isolated executor; no actuation in this work |
| Bot kill/restart during adopted control | Requires separately approved safety-isolated executor; no process/service operation in this work |

The #68 canonical issue text was not present in this offline repository
checkout. Available in-tree authority/evidence includes
`tools/acceptance_guard/REVIEW.md`, `docs/assistant/PHYSICAL_TEST_CONTROL.md`,
and the 2026-10-14 synthetic raw-protection receipt. This record does not
claim to reproduce or supersede issue #68.

## Offline checks attempted

- `tests.test_d061_takeover_smoke`: **45 passed** on the requested deployment
  venv (`/home/home-pc/rd6018-v3-deploy/.venv/bin/python`).
- Focused control-plane tests were also attempted. Three tests bind fixed
  `/run` socket paths and failed with sandbox `PermissionError`; setting the
  documented socket override did not affect those tests because their
  constructors explicitly use the fixed default.
- Full unittest discovery was attempted with dummy HA/Telegram environment.
  It produced partial progress and the same fixed-path permission errors, then
  stalled without emitting a final unittest summary. It is not recorded as a
  pass.
- `git diff --check`: passed.

The restricted Codex sandbox could not complete the full suite. An independent
self-hosted WSL2 run *outside that sandbox* completed successfully using the
existing Python environment and dummy CI credentials:

- Focused `test_d061_takeover_smoke`, `test_physical_test_fault_injection`,
  `test_d061_restart_off_audit`: **55/55 PASS**, 0.545 seconds.
- Full `unittest discover -s tests -p 'test_*.py' -q`: **1735/1735 PASS**,
  66.991 seconds, exit 0.
- `git diff --check`: exit 0.

Immutable local evidence from the independent run is at
`/var/tmp/d061-negative-matrix-20261014-validated/{focused.log,full.log,result.txt}`.
These tests verify the existing production and acceptance baseline; the proposed
next two supervised physical fault modes have **not** been implemented, unit-tested
as runner scenarios, or exercised electrically. Never infer their PASS from the
baseline suite. Nothing in these offline checks demonstrates new hardware behavior.