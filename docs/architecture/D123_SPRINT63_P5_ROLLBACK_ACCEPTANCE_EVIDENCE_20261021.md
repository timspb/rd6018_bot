# D123 Sprint 63 — P5 source closure and rollback acceptance

## Scope

Source-only review began from clean HEAD
`1b2f8a9f096cb0db690db79ed65dc1288c0667eb` in the writable WSL2 worktree.
No production/deployment host, node104, ESP, HA, firmware, network, GitHub,
dependency installation, service operation, or physical Output was involved.
Guarded restore's OFF latch and absent production resume endpoint were left
unchanged. P2/P4 were not re-audited.

The P5 checklist, `docs/DEPLOYMENT.md`, existing release/staging owner
`tools/node104_atomic_deploy.py`, D090 transaction owner
`tools/node104_d090_transaction.py`, and isolated atomic transaction simulator
were reviewed for actual behavior. No second installer or release framework
was created.

## Source review result

No concrete source defect remained in the requested boundary:

- **Candidate identity and install preparation:** the existing stage path
  resolves a Git commit, creates its archive from that exact commit, verifies
  archive digest and extracted path/mode/size/content manifest, then writes
  the staged marker. The generic atomic simulator exposes no production
  activate/install/rollback operation. Its `simulate` CLI remains disabled.
- **Current preimage identity:** D090 does not infer the currently installed
  preimage from a historical source SHA. `verify_pinned_preimage_app` requires
  the reviewed app inventory digest and rejects a missing or mismatched pin;
  transaction prepare also verifies the observed app against that pin. The
  old SHA marker alone is not accepted as the app-tree preimage proof.
- **Complete backup:** D090 captures a baseline inventory, flushes the backup
  tree before journaling it durable, and compares the backup inventory and
  app/state/venv/configuration digests to that baseline before restoration.
  Partial/unsealed backups are not rollback material. Corrupt or missing
  durable backups leave the service contained for review.
- **Failure and recovery behavior:** existing tests inject failures at journal,
  backup, swap, service, and restore boundaries. They exercise preimage drift,
  stale proof, truncated/unsealed backup, backup corruption, idempotent
  recovery, and crash points. The separate temporary-root simulator covers
  atomic rename recovery and journaled backup corruption. This is offline
  software evidence, not production rollback acceptance.
- **Safety gate:** existing release and D090 tests preserve prepare-only
  behavior and require fresh independent OFF evidence for any live transaction.
  This sprint performed no live preflight and grants no deployment authority.
- **Dry run:** source staging plus D090/D105 behavioral simulations cover the
  available offline path. There is no supported production install or rollback
  dry-run command to exercise; adding one would create a new owner outside the
  existing release boundary.

Conclusion: **SOURCE-ONLY P5 EXHAUSTED**. No source changes were warranted.
Do not continue with new archive/hash loops absent a new source defect. The
current deployed accepted SHA and durable deployment backup remain
**UNKNOWN / UNPROVEN**; historical SHA or local staging manifests cannot fill
that evidence gap.

## Validation

- Python 3.12 focused release/transaction/rollback/guard batch: **81 tests,
  1 skipped, PASS**. Command covered `test_node104_atomic_deploy`,
  `test_node104_d090_release`, `test_node104_d090_transaction`,
  `test_node104_d105_trial_lifecycle`, `test_node104_d105_stage_trial`,
  Sprint 60 source gates, and Sprint 58/59 guarded activation/resume tests.
- Outer canonical Python 3.12 full discovery: **2,492 tests, 3 skipped, PASS**, 104.482s. Log `/tmp/d123-s63-canonical.log`. Supersedes the incomplete Codex sandbox run.
- Python 3.12 `compileall -q .`: **PASS**.
- `git diff --check`: **PASS**.
- Python 3.10 and 3.11: **BLOCKED**, interpreters unavailable. No packages or
  interpreters were installed.
- Worktree changes are documentation only and remain uncommitted for the outer
  runner.

## External release gates still required

1. Separately authorized read-only inventory of the live installed tree/SHA,
   service release journal, and complete durable backup with its preimage
   relationship.
2. On any separately authorized deployment, follow existing
   `docs/DEPLOYMENT.md`: preserve the service manager/name and runtime state,
   capture and verify the current preimage, stage the exact committed
   candidate, and pass direct ESP Native preflight plus fresh post-stop OFF
   proof before the existing transaction.
3. Run the supported Python 3.10/3.11/3.12 matrix and canonical full test suite
   on the exact committed candidate. Missing interpreters remain BLOCKED.
4. Compile, flash, and bench-validate the exact matching ESPHome contract
   before any lease/live-adoption deployment.
5. Perform separately authorized supervised physical acceptance. Source tests
   do not establish `Output OFF`, deployment readiness, or `PHYSICAL PASS`.

Status: **SOURCE-ONLY PASS (full Python 3.12 suite); Python 3.10/3.11 BLOCKED; deployment and physical acceptance BLOCKED/out of scope.**
