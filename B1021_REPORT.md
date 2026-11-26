# B1021 — P9 Git classification and source-release hygiene

Date: 2026-11-26
Scope: this isolated clone's committed tree and local Git metadata only. No
network/GitHub request, test, source edit, staging, commit, push, branch
mutation, deployment, node104/ESP/HA, or hardware action was performed.

## Decision

**Finite classification complete for this clone. No demonstrated tracked
generated artifact or private secret requires deletion. No code cleanup is
justified.** Keep P3/P8 HOLD and do not merge PR #182 to main or treat this as a
release.

The current canonical P9 status line is **“НЕ ЗАВЕРШЁН; ДОПУСКАЕТСЯ ТОЛЬКО
ПОСЛЕ КЛАССИФИКАЦИИ WIP И RELEASE CANDIDATE”**. Its only unchecked criterion
reads:

> “Очистку Git, commit и push выполнять отдельно после классификации и явной
> проверки назначения; не затрагивать чужие upstream.”

Two distinct conclusions follow:

1. **Classification/destination workflow criterion: evidence supports treating
   the already performed separate feature-branch commit/push as satisfying
   this criterion, subject to controller reconciliation.** Locally, HEAD
   `775c856c14a2d4ab78e2e335a7bd6deda58c7fd2` is a clean, single-parent
   fast-forward continuation of `383d1613488062596d710cf97ad2c4778eea08dd`;
   the requested task states that this exact accepted head is on the main-based
   draft PR #182, with its destination verified and CI #2243 plus ESPHome #162
   successful. The commit history shows no merge commit or unrelated branch
   ancestry. These PR/CI/destination facts are supplied task evidence, not
   independently queried here. The B1018 report records that this workflow was
   explicitly reserved for a separate task. Closed PR #181 is the superseded
   prior candidate per task context and is not a current cleanup destination.
2. **Final main integration/release is still open and must wait.** The local
   clone contains no `origin/main` ref, and `origin` is configured as a local
   path to the B1018 workspace; therefore this report cannot establish current
   main ancestry or current remote PR state by local Git evidence. More
   importantly, main merge/release is not needed to satisfy the quoted
   separate-classification/push criterion and is gated by unresolved P3/P8
   acceptance. Do not merge, deploy, or claim release. Do not silently change
   the canonical checkbox: the controller owns status reconciliation.

This is not a request for more inventory. If the controller accepts the
task-supplied destination verification, there is no remaining P9 Git cleanup
action identified in this clone; only canonical status reconciliation and the
separately gated main/release decision remain.

## Exact local Git evidence

- Worktree/index at inspection start: clean (`git status --short --branch`);
  the only untracked path now is this requested `B1021_REPORT.md`.
- Branch: `codex/rd6018-b1021-git-p9-20261126`.
- HEAD: `775c856c14a2d4ab78e2e335a7bd6deda58c7fd2`.
- Sole parent: `383d1613488062596d710cf97ad2c4778eea08dd`.
- Local branch and `origin/codex/rd6018-b1018-architecture-closure-20261126`
  both point to HEAD. The B1018 branch ref also points to HEAD.
- `origin/HEAD` points to that feature ref. `origin/main` is absent; `git
  merge-base HEAD origin/main` cannot be evaluated. No fetch was attempted.
- The local B1018 report says the prior task had no remote comparison, commit,
  or push. It records PR #182 as a later intended destination; the current
  supplied task facts state that the separately committed/pushed result is now
  on that draft PR.
- `git diff 383d161..775c856` contains only the B1018 report, synchronized
  authority/status documents, and six D123 architecture-test location
  corrections. No generated build output or secret path appears in that delta.
- The requested head is the end of the local feature lineage; no separate
  cleanup commit, branch delete, reset, rebase, or main merge was made here.

## Path classification

| Class | Local findings | Disposition |
|---|---|---|
| Safe to delete now | None proven. | No deletion. Age, historical naming, and non-import status are not grounds for removal. |
| Retain: secret templates | Tracked names only: `config/secrets/README.md`, `esphome/secrets.example.yaml`. | Retain as documentation/templates. Their contents and any real private secret files were not read. `.gitignore` excludes `.env`, `.env.secrets`, `env.secrets`, `.secrets/`, `config/secrets/`, `*.secret*`, `node101.env`, and `esphome/secrets.yaml`. A clean worktree does not establish whether ignored local secret files exist. |
| Retain: source and tests | 1,754 tracked paths total. Filename-only scan found no tracked `build/`, `dist/`, virtualenv, bytecode, coverage, database, log, or test-result output. | Keep. These are committed project inputs, not cleanup candidates. |
| Retain: fixtures / reproducibility inputs | `tests/fixtures/architecture/ownership_history/source_3c692554074b27805419a9b0767133a1c8d78150.tar.gz` and JSON/CSV fixtures are tracked. | Retain as test/history inputs; do not mistake the tarball for a generated deployment bundle based on extension alone. |
| Retain: release / deployment tooling | `.github/workflows/release.yml`, `tools/node104_release_admission.py`, `tools/node104_d090_release.py`, `tools/node104_atomic_deploy.py`, and related release tools are tracked source. | Retain. They are owners/tooling, not disposable build output. None was executed. |
| Retain: local-only ignored workspace | `.recipe-studio-local/` is ignored by `.gitignore`. | No scan or read of its private contents. It is explicitly excluded from publishing/deployment. |

No real secret contents were read, copied, or recorded. The filename-only pass
did not enter ignored secret/private directories.

## Documentation and release consistency

- `README.md` identifies `python bot.py` as the production entrypoint and
  directs deployment to `docs/DEPLOYMENT.md`; `docs/README.md` classifies
  current authority versus historical/evidence docs and points to the same
  deployment/failsafe authorities. This is consistent with the repository's
  modular production model.
- `docs/DEPLOYMENT.md` separates source/software evidence from physical
  acceptance and deployment, requires direct ESP Native evidence for physical
  operations, and gives rollback procedures. Its dated operational baseline
  is historical evidence, not a fresh node query in this task.
- **One stale documentation candidate was identified:** `RELEASES.md` still
  labels an old 2026-03-07 change list “Unreleased”; it describes automatic
  OVP/OCP offset programming and forced Ca/Ca/EFB Mix transitions. Those
  statements conflict with the current owner canon, which explicitly excludes
  OVP/OCP from software protection/charge admission and forbids automatic
  threshold programming. `RELEASES.md` is consumed by the tag-based release
  workflow for exact matching tag headings, so the stale section is not itself
  proof of a current release. **Retain it as historical until release owner
  review; do not delete or publish it as current release notes.** A focused
  release-note correction is the only concrete follow-up candidate, and should
  be made in a separately authorized documentation change after confirming
  whether the section is intended as an old historical entry or a draft. No
  source behavior is changed by this report.
- README text about an existing release manifest/source identity is retained as
  current release documentation; this inspection does not treat it as
  authorization to add any new signature, hash pin, or release gate.

## Cleanup scripts and release actions

The local filename/content search found no script that deletes Git branches or
performs repository-wide `git clean`, reset, or push. Matches for cleanup are
runtime/test transaction cleanup or remote staging cleanup in a physical
acceptance tool, not repository cleanup. They were not run. `release.yml`
publishes on version tags or manual dispatch; it does not merge branches or
clean the Git worktree. The only deployment documentation commands that can
discard work (`git checkout --detach` / `git reset --hard`) are node deployment
instructions and were not executed.

## Boundary and next action

PR #182 remains DRAFT per task context. Its stated successful CI and ESPHome
checks establish source CI only; they do not satisfy P3/P8 physical/release
acceptance. Keep P3, P8, and the aggregate P9 status on HOLD until the
controller reconciles this classification against the canonical checklist.
After P3/P8 acceptance, the owner may separately decide main integration and
release. No local Git operation remains justified by the findings in this
report.


## Independent controller disposition — P9 Git workflow accepted

Independently verified GitHub compare `main` ->
`feat/rd6018-rc-full-modularity-20261126`: exactly **21 commits ahead,
zero behind**, with merge base `70074de154b4c6f44614f2b4cfddf6ac77c55fbb`
(the original main HEAD); accepted Draft PR #182 at
`775c856c14a2d4ab78e2e335a7bd6deda58c7fd2`, GitHub CI #2243
and dummy-secrets ESPHome source compilation #162 SUCCESS.
The canonical P9 checklist already recorded classification of original WIP
and acceptance of the separate reviewed-source candidate. Individual
source-only commits were separately reviewed and fast-forward pushed only
to this destination. The controller therefore accepts **the quoted P9
Git-classification/commit/push checkbox** as completed, without claiming
the aggregate P3/P8 physical gates or a main merge/deployment.
Final release acceptance remains HOLD until actual P3/P8 physical evidence.
