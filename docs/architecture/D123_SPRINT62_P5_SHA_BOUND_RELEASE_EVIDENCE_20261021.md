# D123 Sprint 62 — P5 exact-SHA offline release proof

## Scope and identity

Source-only offline work began from exact clean HEAD
`a7cb80e438ca777b6425646a7efc21907c22f743` on
`codex/d118-start-lease-repair-20261019`. The initial tracked/untracked worktree
was clean. P0–P4 were not re-audited. No production host, node104, service,
ESP, HA, firmware, network, GitHub, physical Output, or dependency installation
was involved. No deployment state was modified. The local `.git` is read-only
for this runner; final changes remain uncommitted for the outer runner.

## Independent archive and source manifest

Created the deterministic `git archive --format=tar` for the exact 40-character
SHA in a temporary directory. Independently parsed every regular tar member,
computing archive SHA256 and sorted manifest entries of relative path, mode
(`& 0777`), byte size, and content SHA256. Compared the resulting complete
object with `tools.node104_atomic_deploy.source_manifest(repo, exact_sha)`;
all fields matched. No symlink or non-regular payload is counted as a regular
source file.

| Artifact fact | Verified value |
|---|---|
| Source SHA | `a7cb80e438ca777b6425646a7efc21907c22f743` |
| Git archive SHA256 | `32101e28f92ceaea98b087ff2b6849f0f47a17423838097626fc3dd95c25ac68` |
| Regular tracked file count | 1,185 |
| Canonical manifest JSON SHA256 | `972ef78faf36061269be4893a8f1db7f4014ab0b0951a9d867b1fdc07bace4cd` |
| Manifest fields | `path`, `mode`, `size`, `sha256` per member, plus schema/node/service/source/archive identity |

The manifest digest is SHA256 of UTF-8 `json.dumps(manifest, indent=2,
sort_keys=True) + "\\n"`, matching the existing staging writer. The exact
archive is a source artifact; it is not a built wheel, installed tree,
virtualenv, firmware image, or deployment acceptance record.

Untracked authority fixture exclusion is covered by the existing
`tests.test_d123_sprint60_source_release` test, which creates a temporary
untracked file below the worktree and verifies that `git archive` omits it.
The fixture is deleted by that test's temporary-directory cleanup. No untracked
local authority file is represented by the source manifest.

## Existing stage and rollback-source audit

Read-only inspection of `/home/home-pc/rd6018-stage-20261018` found two
historical local stage manifests:

| Staged source SHA | Archive SHA256 | Files | Manifest file SHA256 |
|---|---|---:|---|
| `6ab0b1c1704c2e5f18360c1db2fabeb654da696e` | `620a8474a2f5a8ab6b4b796a2c1883f91a9e57ab8ed713eeede6126ddaba86c4` | 1,052 | `a4ffffea4d566c19b34e60c28344a59361c23cd4d86749266d0d7d24639ead60` |
| `f4470d894eec4c37121b51f30493ea848e65baff` | `0e1437a5950d5dc431d18f5983e49a159d0f5611eba24b626dd972d14fa40bca` | 1,051 | `c02afd1d9da4df4038b622d3e8489dbb3a1970b47369da1f1c03c7f0c8b6a775` |

These are historical staged source outputs and their local manifests only.
They do not prove either that a revision was installed or that a backup is the
actual pre-image of a deployment. The existing script's `source_manifest` and
`stage` bind exact source SHA, archive bytes and manifest digest. The offline
transaction simulator persists a backup manifest before swapping, validates
backup containment/content during recovery, and restores fail-closed/idempotently.
Its CLI offers `manifest`, `preflight`, `stage`, `recover`, and `simulate`;
there is no production activation or rollback command. The simulator's green
tests therefore prove software behavior only, not a node rollback.

Current installed accepted SHA: **UNKNOWN / UNPROVEN**.
Current durable deployment rollback backup/path and its relationship to the
installed pre-image: **UNKNOWN / UNPROVEN**. Historical `c1298ea...` and
`8b75cca...` values in prior records remain non-current references. Resolving
this requires fresh read-only inventory from the actual deployment host,
including installed revision/tree identity, service release journal/manifest,
and a durable complete backup manifest tied to the pre-image. That proof is
outside this offline boundary.

The deployment runbook still requires direct fresh ESP Native preflight and a
distinct fresh post-stop OFF proof, exact edge-firmware compile/flash/bench
acceptance, preservation of service/runtime state, and exact source/testing
before any future deployment. None is asserted here.

## Guarded restore and resume boundary

Existing Sprint 60 architecture tests and source inspection confirm guarded
restore remains activated-OFF: the shared ExecutionPort latch blocks ON paths,
startup does not execute the physical-resume transaction, and production does
not install a guarded-resume endpoint. Sprint 59 evidence remains the authority
for the transaction design. No source result here clears either latch or proves
physical resume.

## Python and checks

Python 3.12.3 is available locally (`/usr/bin/python3.12` and the existing
`/home/home-pc/.venvs/pcp-test` environment). No Python 3.10 or 3.11 executable
was found; both are **BLOCKED**, not passed. No environment or dependency was
installed.

Focused Python 3.12 command covering the existing Sprint 60 source gates,
atomic deploy simulator, D090 release, Sprint 58 activation architecture, and
Sprint 59 resume tests completed **38 tests, 1 skipped, PASS**. An initial
invocation named a nonexistent Sprint 58 test module and failed import; it was
corrected to the actual `test_d123_sprint58_guarded_activation_architecture`
module, and the passing result above is from the corrected command.

Outer canonical Python 3.12 discovery on the exact Sprint 62 worktree: **2,492 tests, 3 skipped, PASS**, 108.345 s; log `/tmp/d123-s62-canonical.log`. This supersedes the incomplete Codex sandbox discovery.
`python3.12 -m compileall -q .` and `git diff --check` both passed.

## Boundary and next evidence

This proves exact committed source artifact identity and local offline rollback
simulator behavior only. It does not prove installed source, deployment backup,
service state, firmware contract, direct Native physical telemetry, or Output
state. Next source boundary is outer-runner commit, followed by regenerating
this archive/manifest against that exact committed SHA and recording its hashes.
A separate authorized read-only deployment inventory is required to resolve
the installed SHA and backup. No production, service, ESP, HA, network,
firmware, or physical action is authorized by this evidence.
