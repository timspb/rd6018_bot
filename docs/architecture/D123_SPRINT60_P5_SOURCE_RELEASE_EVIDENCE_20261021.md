# D123 Sprint 60 — P5 source release and rollback preparation

## Scope and source identity

Source-only work began from clean HEAD
`ec21585957f5994edfde6bfaf8888b0a69e8b63b` on
`codex/d118-start-lease-repair-20261019`. No node104, ESP, HA, firmware,
service, deployment, GitHub, network, or physical Output was accessed. No
package was installed. P0–P4 were not re-audited; the owner map and prior
Sprint 55C / Guard P2 / Sprints 57–59 evidence are referenced as authorities.

The source-to-release matrix for the candidate is:

| Gate | Required evidence / pinned value | Sprint 60 result |
|---|---|---|
| Source | Exact clean base `ec21585957f5994edfde6bfaf8888b0a69e8b63b`; release candidate must be the exact committed Sprint 60 HEAD, with clean tracked and untracked state recorded before staging | Base verified; final candidate SHA is the HEAD containing this evidence and must be recorded by outer commit runner |
| Install artifact | Existing `tools/node104_atomic_deploy.py` stages `git archive --format=tar <SHA>`, records archive SHA256 and sorted tracked-file path/mode/size/content SHA256 manifest, then verifies the extracted tree against that manifest | Reused; untracked test-authority files cannot enter a `git archive`; no secondary packager added |
| Artifact hash inputs | Candidate commit SHA; Git archive bytes/SHA256; each tracked archived file's relative path, mode, size and SHA256; generated release manifest and marker digests | Exact values are candidate-build outputs and are deliberately not fabricated before the outer runner commits/stages the exact candidate |
| Python compatibility | Existing `.github/workflows/ci.yml` matrix: 3.10, 3.11, 3.12; requirements pins `aioesphomeapi==36.0.1` below 3.11 and `46.2.0` at/above 3.11 | 3.12 run locally; 3.10/3.11 blocked because interpreters are absent; no CI/GitHub invocation |
| Rollback preconditions | Capture exact currently installed accepted SHA/tree and a durable verified backup; candidate SHA must differ and be recorded separately; preserve service, environment, state and runtime data; use the documented existing transaction and normal safety prechecks | Historical last confirmed deployed SHA in `V3_PROJECT_RUNBOOK.md` is `c1298ea2df67bba1e4888de6e830b002b5db2fce` (2026-10-04 checkpoint); later D090 evidence observed marker `8b75cca153f00847d84396aba392472bb7552ad` (2026-10-17). These are historical and conflicting snapshots, not current installed-state proof. Current installed accepted SHA and backup are unavailable under this read-only boundary. |
| Startup containment | Guarded software restore may activate only behind the shared OFF latch; production physical resume endpoint remains uninstalled; startup and background tick cannot resume from saved state | Existing Sprint 58/59 guarantees retained; source gate added |
| Physical/deploy evidence | Current direct ESP Native evidence, exact target firmware compile/flash/bench acceptance, deployed service validation and exact installed SHA | Missing by explicit scope. No deploy-ready or physical-ready claim. |

## Rollback and operator checklist

Use the existing `docs/DEPLOYMENT.md` and offline `tools/node104_atomic_deploy.py`
transaction. Do not use the historical SHA values above as a current pre-image.

1. Before a future separately authorized rollout, record the live installed
   accepted SHA as `PREVIOUS_SHA`, capture and verify the complete durable
   rollback backup, and record the candidate as a distinct exact `CANDIDATE_SHA`.
2. Confirm the candidate archive and tracked-file manifest hashes match the
   exact committed SHA. Confirm no untracked/local authority fixture is in the
   artifact; `git archive` includes committed tracked files only.
3. Run the supported Python matrix and existing compile/full tests on that
   exact candidate. Keep any missing interpreter/dependency result BLOCKED.
4. Before any deployment, perform the current direct ESP Native preflight and
   separate fresh post-stop OFF proof required by `docs/DEPLOYMENT.md`. They
   are intentionally absent from this source-only evidence.
5. Preserve the installed service manager/name, environment, databases and
   session state. Deploy only through the existing release transaction after
   the exact ESPHome contract compile/flash/bench boundary is independently
   accepted.
6. On failure, stop the failed candidate, restore the verified
   `PREVIOUS_SHA`/backup using the existing rollback transaction, restart the
   existing service, verify service/log state and report both SHAs. Never
   treat a green source suite as deployment or physical acceptance.
7. Confirm guarded restore remains activated-OFF and the production resume
   endpoint remains absent. Physical resume stays fail-closed.

## Source-only gates and validation

`tests/test_d123_sprint60_source_release.py` adds deterministic offline gates
for the existing archive/manifest boundary, one production host and canonical
session writer, Guarded restore OFF latch / absent production resume endpoint,
and the existing Python matrix. Existing Guard Sprints 57–59 tests remain the
behavioral authority; no production behavior changed.

Validation results for this exact worktree are recorded below. Passing source checks establish **source-ready only**. Deployment readiness
still requires current installed SHA/backup, exact artifact staging and the
documented live safety prechecks. Physical readiness additionally requires
separate direct Native evidence and exact-target firmware/bench acceptance.

## Results

- Base HEAD: `ec21585957f5994edfde6bfaf8888b0a69e8b63b`.
- Candidate final commit SHA: supplied by outer commit runner; not available
  during this source-only edit.
- Python 3.10: BLOCKED — interpreter absent; no package installation.
- Python 3.11: BLOCKED — interpreter absent; no package installation.
- Python 3.12 focused release/Guard/startup/restore/rollback batch:
  **110 tests, 1 skipped, PASS** using the existing `/home/home-pc/.venvs/pcp-test`
  environment. This includes actual `git archive` exclusion of a temporary
  untracked authority fixture.
- Python 3.12 canonical full discovery (outer WSL venv): **2,491 tests, 3 skipped, PASS**, 104.861s; log `/tmp/d123-s60-canonical.log`. This supersedes the incomplete Codex sandbox runs.
- `python -m compileall -q .`: PASS.
- `git diff --check`: PASS.
- Source-ready: **PARTIAL** — 3.12 canonical suite passes; Python 3.10/3.11 and exact committed artifact checks remain outstanding.
- Deployment-ready: NO. Physical-ready / PHYSICAL PASS: NO.
