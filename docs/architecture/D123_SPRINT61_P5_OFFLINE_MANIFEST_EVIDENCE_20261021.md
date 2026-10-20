# D123 Sprint 61 — P5 offline manifest and rollback provenance

## Scope and source identity

This is source-only offline evidence for the requested clean base
`02f26307c770693b471e519f38dfbe44b69dc810` on
`codex/d118-start-lease-repair-20261019`. No production/deployment host,
node104, ESP, HA, firmware, service, network, or physical Output was accessed.
No dependency was installed and no deployed asset was modified. The checkout
was clean at the requested base. The final WIP remains uncommitted because the
`.git` directory is read-only in this runner.

The exact base archive was created with the existing
`tools/node104_atomic_deploy.py manifest` / `git archive --format=tar` path.
Its verified values are:

| Item | Value |
|---|---|
| Source commit | `02f26307c770693b471e519f38dfbe44b69dc810` |
| Git archive SHA256 | `a36eee34deb9f4b11380d075985126d12aa00f46a8aff411f0bfcaac1bbe26d8` |
| Sorted source manifest file count | 1,184 |
| Exact generated source-manifest JSON SHA256 | `3df12215c5955cc776764a741525cac93532f9f75a72d2d6d1c02bba8dd1f4b1` |
| Manifest fields | path, mode, size, content SHA256 for every regular archive file |

An independent offline parse of the exact archive compared its complete member
set and each path/mode/size/content digest with the generated manifest; all
1,184 entries matched. `git archive` contains committed tracked source only.
The initial worktree had no untracked files; the existing Sprint 60 test also
creates an untracked authority fixture and confirms it is excluded. Local test
authority files, ignored state and secrets therefore do not enter this source
archive. These are **source archive** hashes, not deployment-built output,
wheel, virtualenv, firmware, or installed-tree hashes.

The existing extracted-tree verifier checked path set, size and bytes but did
not compare file modes. This sprint adds mode comparison and a regression that
proves a mode change rejects the tree. No new release framework or installer
was introduced.

## Local release and rollback provenance

Read-only inspection found two local staging manifests under
`/home/home-pc/rd6018-stage-20261018/`:

| Local staging source SHA | Archive SHA256 | Files | Provenance meaning |
|---|---|---:|---|
| `6ab0b1c1704c2e5f18360c1db2fabeb654da696e` | `620a8474a2f5a8ab6b4b796a2c1883f91a9e57ab8ed713eeede6126ddaba86c4` | 1,052 | Historical staged source manifest only |
| `f4470d894eec4c37121b51f30493ea848e65baff` | `0e1437a5950d5dc431d18f5983e49a159d0f5611eba24b626dd972d14fa40bca` | 1,051 | Historical staged source manifest only |

These manifests do not identify the currently installed tree, an accepted
deployment, or a verified rollback backup. The previously cited
`c1298ea2df67bba1e4888de6e830b002b5db2fce` and
`8b75cca153f00847d84396aba392472bb7552ad` remain historical references only.
Current installed accepted SHA: **UNKNOWN / UNPROVEN**. Rollback backup:
**UNKNOWN / UNPROVEN**. Missing proof is a separately authorized read-only
inventory from the actual deployment host containing the installed commit or
tree identity plus its release journal/manifest, and the durable backup path
with a verified complete tree manifest and relationship to that installed
pre-image. No such host evidence was accessible within this source-only
boundary; no deployment acceptance is asserted.

## Python matrix and validation

| Python | Local status |
|---|---|
| 3.10 | **BLOCKED** — no interpreter found |
| 3.11 | **BLOCKED** — no interpreter found |
| 3.12.3 | Available at `/home/home-pc/.venvs/pcp-test/bin/python`; `aioesphomeapi`, `telegram`, and test dependencies imported successfully |

The focused batch
`tests.test_d123_sprint60_source_release`,
`tests.test_node104_atomic_deploy`, and `tests.test_node104_d090_release`
completed **27 tests, 1 skipped, PASS**. `python -m compileall -q .` and
`git diff --check` passed. Canonical Python 3.12 full discovery was attempted,
but stalled without a final unittest summary; the process disappeared while
the runner session remained open and had to be interrupted. Result is
**INCOMPLETE / no test count available**, not PASS. No versions were installed
or fetched.

## Offline acceptance and rejection conditions

For this source base, acceptance means the exact revision resolves to the
pinned SHA; archive bytes hash to the recorded SHA256; archive member paths,
modes, sizes and content hashes equal the source manifest; the extracted tree
has exactly that file set and metadata; and required source checks pass on
available supported Python versions. Reject on any SHA mismatch, extra/missing
archive or tree entry, path traversal, unsupported member/symlink, mode/size/
content mismatch, test/compile failure, or untracked authority material being
represented as committed source. Missing Python versions remain BLOCKED, not
PASS.

These conditions prove source artifact integrity only. Deployment still needs
the actual installed SHA and durable backup provenance, exact candidate
release staging, current direct ESP Native preflight including fresh
post-stop OFF evidence, firmware contract compile/flash/bench validation,
and the documented deployment transaction. This sprint supplies none of those
live or physical proofs.

## Next concrete source-only gate

After the outer runner commits the WIP source cut, rerun the existing manifest
command against that exact new committed SHA and pin its archive/manifest
hashes. Rerun full Python 3.12 discovery there; run Python 3.10 and 3.11 only
if already-functional environments become available. Keep current installed
SHA and rollback backup unproven until their separately authorized read-only
deployment inventory is supplied.

## Results

- Python 3.12 focused: **27 tests, 1 skipped, PASS**.
- Python 3.12 canonical discovery (outer project venv): **2,492 tests, 3 skipped, PASS**; log `/tmp/d123-s61-canonical.log`. Earlier Codex sandbox run was incomplete.
- Python 3.12 compileall: **PASS**.
- `git diff --check`: **PASS**.
- Python 3.10 and 3.11: **BLOCKED**, interpreters unavailable.
