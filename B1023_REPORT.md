# B1023 — CURRENT HEAD source-paired D145/D124 release preparation

Run: `rd6018-b1023-20261126-r73-source-paired-release`
Branch: `codex/rd6018-b1023-source-paired-release-20261126`
Base/current source HEAD: `a5364c8cdc2e062a91aaef9861b1dd39e137fd91`
Initial worktree: clean; no source changes made.

## Result

Prepared an exact offline source archive/tree for the requested current HEAD
using the existing offline `node104_atomic_deploy.stage` function. The source
manifest/tree verification completed successfully for 1,759 tracked files.
Added a unique B1023 D124 profile skeleton and readiness plan. The skeleton
contains the candidate SHA, archive digest, and serialized stage-manifest
digest derived from this source, and explicit `NOT VERIFIED` markers for every
node-dependent value. It is deliberately not a valid D124 profile.

The existing D124 schema is sufficient; no source tooling change is needed.
The D145 entrypoint is not reusable for this candidate: it pins the historic
D146 D138 source `d351c208cbf8666f881a4660df6a0b211170e857`, profile digest,
preimage and candidate identity. Blindly repinning it would neither provide
the missing live observations nor resolve source/tool pairing. Historical
D146 evidence remains untouched.

## Required unknowns

The installed composite app+venv/state preimage and D144 release identity,
actual firmware identity, current service Python, systemd unit and `.env`
metadata, exact installed D147/D151 collector artifacts, and actual old-source
to-candidate changed-path list are **NOT VERIFIED**. Historical D137/D146
records are not current observations. A D138 app+venv stage has not been
created; the produced generic source stage is not a replacement for it.

## Evidence

- Candidate: `a5364c8cdc2e062a91aaef9861b1dd39e137fd91`.
- Offline stage:
  `/tmp/rd6018-b1023-source-pair/release-a5364c8cdc2e062a91aaef9861b1dd39e137fd91-bafmkme0`.
- Source archive SHA-256:
  `5b4d9c3687c3168c7d07cb200dcc39be54f7b632e538e4f8d70d1694f03e4f7f`.
- Serialized stage manifest SHA-256:
  `f390fdb839b52ee4d6aca78ed8e1995f2a6cdec6ac30834def1687bc9fbb2c2c`.
- Manifest schema: 3; `STAGED_OK` schema: 2; file count: 1,759; stage
  tree verified by the existing helper.
- D147/D150/D151 tracked observer versions are distinct. Current tracked
  expected hashes are D147 `1127e9e3…`, D150 `d9d4190c…`, and D151
  `9500454a…`; actual installed copies are **NOT VERIFIED**.
- Existing profile loader contract inspected. Historical profile and entrypoint
  were not edited.
- Focused D124 tests and `git diff --check`: results recorded below.

## Validation and limits

This is offline source preparation only. No SSH, remote/GitHub access, node104,
ESP Native API, HA, service, firmware, RD6018, Output, V/I, setpoint, lease,
deployment, `git add`, commit, or push operation occurred. P3/P8 physical and
release gates remain HOLD. P0–P9 stays 98/103 per the supplied current status;
three P3 and two P8 conditions remain open. Draft PR #182, CI #2244 and
ESPHome dummy build #163 are task-supplied context, not queried by this run.

Validation completed:

- Project venv: `/home/home-pc/.venvs/pcp-test/bin/python` (Python 3.12.3).
- `PYTHONPATH=.:tests:tools ... -m unittest tests.test_d124_software_release_profile`:
  **8/8 PASS**.
- Re-opened the exact `/tmp` staged manifest and marker and reran the existing
  `verify_manifest` against the staged tree: **PASS**; `STAGED_OK` reports
  `tree_verified=true` and `directory_fsync=true`.
- Existing `load_software_release_profile` on the B1023 skeleton:
  **BLOCKED as expected** (`release profile node/firmware/lease identity
  differs`). The incomplete skeleton was not admitted.
- `git diff --check`: **PASS**. Python whitespace scan and JSON parse for all
  three new artifacts: **PASS**.
- Final worktree contains only the three unique B1023 report/readiness/skeleton
  files; no tracked source or shared checkpoint/master/handoff/runbook changed.

See [`docs/acceptance/B1023_SOURCE_PAIR_READINESS.md`](docs/acceptance/B1023_SOURCE_PAIR_READINESS.md)
and [`docs/acceptance/B1023_SOURCE_PAIR_PROFILE_SKELETON.json`](docs/acceptance/B1023_SOURCE_PAIR_PROFILE_SKELETON.json).



## Controller reconciliation — avoid self-referential source/profile SHA

This report captures an offline test of the **historical B1023 task base**
`a5364c8cdc2e062a91aaef9861b1dd39e137fd91`, not the now newer
feature-branch HEAD. The tracked JSON skeleton is **intentionally INVALID
and source-neutral**: source SHA, source archive and staged-manifest SHA are
marked NOT VERIFIED. A source-paired profile containing its own current
archive SHA cannot safely be pinned inside the same tracked release archive
because that would change the source SHA again. After all code and release
docs are frozen, generate the complete source-paired profile as a
**separate out-of-tree acceptance artifact**, using independently observed
node104 preimage, service, firmware and collector identity; do not repin the
historical D145 profile or mistake an offline skeleton for admission.
