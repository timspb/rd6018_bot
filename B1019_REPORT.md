# B1019 — Offline release, rollback, and DR rehearsal

Date: 2026-11-26 (Asia/Vladivostok)
Scope: source-only/offline; no node, network, deployment, service, firmware, or physical operation.

## Result

**Offline manifest generation: PASS. Rollback/recovery fixtures: PASS. Full release staging: PASS on mode-preserving WSL /tmp; /mnt/e stage remains HOLD due to filesystem permissions.**

The existing `tools/node104_atomic_deploy.py` route generated a schema-3 manifest from the exact clean feature HEAD and produced a deterministic archive identity. Its `stage()` path then stopped at the first extracted-tree mode comparison. The checked-out worktree is on `/mnt/e`; this filesystem reports mode `0777` after `chmod 0664`, while Git archive records `0664`. This demonstrates a mode-preservation limitation in this rehearsal environment, not a proven source packaging defect. The stage was not marked complete (`STAGED_OK`); no source change is justified by this evidence.

## Baseline and scope

- Branch: `codex/rd6018-b1019-release-repro-20261126`
- HEAD: `775c856c14a2d4ab78e2e335a7bd6deda58c7fd2`
- Initial `git status --short --branch`: clean; exact branch above.
- Tracked paths: 1,754. Git symlinks: 0.
- Python: `python` was absent (first invocation exit 127); `python3 --version` returned `Python 3.12.3`.
- No external project files or user data were accessed. Explicit archive/package and rollback fixtures were created under uniquely named directories inside this worktree and removed. The existing `source_manifest()` implementation internally uses `TemporaryDirectory()` without a `dir`, so its short-lived duplicate archive uses the Python system temp location and was automatically cleaned. I also ran `git archive` directly to a temporary path inside this worktree and validated it there.
- No tests or CI were run. The task context reports GitHub CI #2243 and ESPHome source build #162 successful; they were not independently queried here.

## Manifest and package evidence

Commands/evidence:

```text
git status --short --branch
git rev-parse HEAD
git branch --show-current
git ls-files
python3 tools/node104_atomic_deploy.py manifest --repo <this-worktree> --sha 775c856c14a2d4ab78e2e335a7bd6deda58c7fd2
```

The last command was run with its JSON redirected to a temporary file inside the worktree; exit **0**, empty stderr. Result: schema `3`, node `node104`, service `rd6018-bot`, source SHA `775c856c14a2d4ab78e2e335a7bd6deda58c7fd2`, **1,754 files**, archive SHA `393d6eb2e351167b9da1423ecee57cc88b220438f963c3288e414df9978d0f78`.

The `source_manifest()` result path set matched `git ls-files` exactly: 1,754/1,754, no missing or extra paths. A separate `git archive --format=tar <exact-HEAD>` written inside a temporary directory under this worktree also produced archive SHA `393d6eb2e351167b9da1423ecee57cc88b220438f963c3288e414df9978d0f78`, with 1,754/1,754 tracked paths and zero symlink members. The stage implementation wrote its `git archive` tar and confirmed the same archive SHA before extraction. Its next `verify_manifest()` check raised the following error; the stage harness exited **1**:

```text
RuntimeError: manifest mismatch: .gitattributes
```

Mode diagnosis: Git index `100644`; archive and manifest mode `0664`; archive bytes and worktree bytes matched (421 bytes); after `chmod 0664`, `/mnt/e` still reported `0777`. Thus the route’s exact-mode extracted-tree verification cannot complete on this mounted filesystem. Do not treat this as a complete stage or package PASS. Expected stage output, if run on a mode-preserving filesystem, is a release directory containing `source.tar`, `RELEASE_MANIFEST.json`, `STAGED_OK`, and verified `tree/`.

Names-only privacy check: no tracked `.env` or `.env.*` path was found. Broader secret-path matches were `config/secrets/README.md` and `esphome/secrets.example.yaml`; their names indicate a README and an example template, respectively. No private-key, credential, password, or token file name was found. File contents and secret values were not searched or printed. The immutable historical `tools/acceptance_guard/source-manifest.json` is a separate D061 pairing asset; it is not this dynamic 1,754-file release manifest and was not changed.

Re-run the source package preparation in a disposable directory on a filesystem that preserves the archive modes:

```bash
TMP="$(mktemp -d /tmp/rd6018-b1019-offline.XXXXXX)"
python3 tools/node104_atomic_deploy.py manifest --repo "$PWD" --sha 775c856c14a2d4ab78e2e335a7bd6deda58c7fd2 > "$TMP/manifest.json"
python3 tools/node104_atomic_deploy.py stage --repo "$PWD" --sha 775c856c14a2d4ab78e2e335a7bd6deda58c7fd2 --staging "$TMP/staging"
```

This is local preparation only. `preflight` consumes evidence, while `stage` only creates a candidate artifact; neither installs or activates it. The atomic tool’s `simulate` CLI intentionally errors with “simulate is library-only”; rollback simulation is through its local API, as exercised below.

## Rollback and recovery rehearsal

Using `SimulationLayout`, `simulate_transaction`, and `recover` directly against isolated temporary fixtures inside the worktree (no tests or live root):

| Journal/crash cut | Recovery result | Prior app restored | Durable backup retained |
|---|---|---:|---:|
| `BACKUP_DURABLE` | `ROLLED_BACK` | yes | yes |
| `SWAP_OLD_RENAMED_BEFORE_JOURNAL` | `ROLLED_BACK` | yes | yes |
| `SWAP_OLD_RENAMED` | `ROLLED_BACK` | yes | yes |
| `SWAP_NEW_RENAMED_BEFORE_JOURNAL` | `ROLLED_BACK` | yes | yes |
| `SWAP_NEW_RENAMED` | `ROLLED_BACK` | yes | yes |

The uninterrupted fixture returned `COMMITTED`, left the candidate tree active, retained the prior backup, and subsequent recovery returned `COMMITTED`. All checks completed with exit **0**. These fixtures establish the simulator’s journaled interrupted-swap recovery and prior-artifact handling only. They do not exercise a production install or a committed-release rollback on node104.

The atomic simulator’s recovery validates the initialized simulation marker, journal identity/state, backup containment and full backup manifest before restoring. Its `recover()` is idempotent for `ROLLED_BACK`/`COMMITTED`. A committed deploy is not reversed by that simulator; use the project’s existing reviewed deployment/known-good revision rollback process for a real release.

## Existing install/update/rollback/DR route

Reviewed sources: `tools/node104_atomic_deploy.py`, `tools/node104_d090_transaction.py`, `tools/node104_d090_release.py`, `tools/node104_d124_release_profile.py`, `tools/node104_d145_entrypoint.py`, `tools/d144_owner_binding.py`, `docs/DEPLOYMENT.md`, and `docs/operations/D145_OWNER_EXECUTION_RECOVERY.md`.

1. **Prepare source locally:** generate an exact-SHA manifest/archive and stage on a mode-preserving filesystem. The atomic deploy script itself has no SSH, systemd, OTA, lease, or actuator implementation. The `preflight` phase is for evidence; it is not a remote deployment command.
2. **Select the existing source-paired owner:** D090/D144/D145 use their established owner/lock and source-paired release profiles. D145’s entrypoint has only `prepare`, `execute`, and `recover`; it checks the node identity and reviewed profile/observer before entering owner logic. Do not substitute the historical D090 CLI for D145 recovery: the D145 runbook explicitly keeps recovery under the shared D090 owner and reads the D144 ledger.
3. **Deployment/rollback:** preserve the existing service, venv, `.env`, state/database/session and service overrides. The general runbook requires exact SHA verification and full compile/unittest preflight before service restart; on startup failure, stop the failed service, restore the prior known-good tree/SHA and prior environment through the documented transaction, restart the same service, then verify service/logs. No legacy runtime flags are a rollback mechanism.
4. **D145 DR recovery:** use the existing D145 entrypoint’s `recover` route for a matching D144 release ledger/profile, not a generic source checkout or simulator. The D145 flow retains state and restores via its owner-bound journal. The separate D146 recovery instructions require fresh direct ESP Native proof and a stopped-phase fresh proof; the saved old report/HA cache is not a substitute. Recovery does not clear quarantine or resume charging.

Reference command shapes from the reviewed runbooks (placeholders must be replaced only by the current approved installed profile/paths during a separately authorized operation; **not run here**):

```bash
# D145/D146 owner-bound recovery entrypoint (node-local operational action)
python3 /opt/services/rd6018-bot/tools/node104_d145_entrypoint.py recover \
  --profile /opt/services/rd6018-bot/docs/operations/evidence/<approved-profile>.json

# D146 documented D090 recovery for its applicable journal/profile path
sudo /opt/services/rd6018-bot/venv/bin/python \
  /opt/services/rd6018-bot/tools/node104_d090_transaction.py recover \
  --python-release-profile /opt/services/rd6018-bot/d090/<reviewed-profile>.json \
  --proof-collector /opt/services/rd6018-bot/d090/node104_d091_physical_proof_collector.py
```

These are alternative, profile-specific existing owners, not interchangeable commands. The current B1019 SHA is not the D145 entrypoint’s pinned source SHA (`d351c208cbf8666f881a4660df6a0b211170e857`), nor the historical D090 source pin. Those profiles cannot be reused to claim B1019 release admission. This report does not select a new profile or authorize an install.

## Remaining readiness evidence / HOLD

- This offline rehearsal did not establish current physical state or bench acceptance. P3/P8 remain HOLD as requested. The existing P0–P9 ledger records the remaining P3 Native programming/readback and causal evidence, authorized R18/OPP/lease hardware gate, and separately authorized physical acceptance; P8 still requires its separate physical acceptance and release acceptance before node104 deployment. No new gate is proposed here.
- The B1019 candidate requires its own reviewed source-paired release evidence/profile and normal release acceptance; existing D145/D090 pins point at other source revisions.
- No node104 current HANDS_OFF, service, or installed SHA readback was made. No deployment/restart, firmware/ESP action, HA access, Output/setpoint/lease operation, network/GitHub access, stage/commit/push, or access to the original dirty `E:/CODEX/rd6018_bot` worktree occurred.
- Final Git cleanup/commit/push is the separate P9 HOLD; this report remains uncommitted.

## Final worktree state

Changed path: `B1019_REPORT.md` only. No production code or canonical checkpoint/runbook was edited. No source modification was made because the observed staging failure is attributable to `/mnt/e` mode emulation and does not prove a reproducibility defect in the package implementation.


## Independent controller retest — staged release VERIFIED on Linux /tmp

The independent controller ran the existing exact-source
`tools/node104_atomic_deploy.py stage` command again, without modifying
production files, using a temporary directory on WSL `/tmp`, which preserves
`chmod 0664`. The result was **STAGE EXIT 0** with empty stderr and a
`STAGED_OK` marker. Verified marker fields:
`schema=2`, `directory_fsync=true`, `tree_verified=true` and manifest hash
`b156403393a4e09f467a235e93c71f0a63ce80898eba1b86f2c26b89785d3944`.
The exact source manifest remained schema 3, 1,754 tracked paths, source HEAD
`775c856c14a2d4ab78e2e335a7bd6deda58c7fd2`, archive SHA-256
`393d6eb2e351167b9da1423ecee57cc88b220438f963c3288e414df9978d0f78`.
The extracted `.gitattributes` mode was `0664`, matching the manifest,
whereas the earlier `/mnt/e` mount reported `0777`. Temporary staging
directory was deleted after verification. No source patch was necessary.

**Result:** offline archive/manifest/stage and the five prior crash-recovery
simulations PASS. This does NOT prove a target node104 deployment, live
install, firmware pairing, production recovery, or P3/P8 physical acceptance.
The candidate was not installed, activated or flashed. The older /mnt/e
failure above is retained as filesystem evidence, not a source packaging
blocker.
