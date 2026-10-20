# D123 Sprint 58 — Guarded restore activation to OFF-only state

## Scope and baseline

Source-only work continued from clean HEAD
`010e5011ccd5e78fe428b7f49bc6edbb1809de10` on
`codex/d118-start-lease-repair-20261019`. No node104, ESP, HA, firmware,
services, deployment, GitHub, network, or physical Output access/action was
performed. No dependency was installed. No recipe, lease duration, protection,
Manual, or ESP-priority behavior changed.

## Transaction shape

The existing `StartupRecovery.replay_deferred_startup_restore` owns the single
transaction under the app-scoped `ExecutionPort._guard_owner_lock`:

1. Require automatic recovery permission, the exact candidate object, and the
   current asyncio task as owner of the already-bound `GuardExecutionOwnerLock`.
2. Read the existing direct ESP Native Guard snapshot API. Require fresh Native
   callback provenance, callback types, and separately fresh armed lease.
3. Read the canonical session and reject missing, retired, stale, or
   candidate/document-mismatched data. Parse both candidate and canonical Guard
   with the existing `read_guard`; require matching session/battery/revision
   and no pending/fault state.
4. Run the existing `assess_main_guard_before_output_on`, which independently
   proves Output OFF, normal protection, and Iset/OCP matching the persisted
   target within the monotone Guard ceiling.
5. Re-read and compare the same candidate object and complete canonical
   document, exact file-byte digest, identities, active state, and Guard
   revision immediately before activation. Issue an immutable
   `GuardedRestoreActivationPermit` bound to those identities, document
   digest, Native evidence generation, current task, and the same held owner
   lock.
6. Install the app-scoped OFF-only latch before mutation. Call the existing
   `ManagedChargeController.try_restore_session` and canonical
   `runtime.charge.persistence.restore_session` with that permit. Persistence
   reconstructs the Guard and revision only from `read_guard` before existing
   continuation and production-extension restoration. Guarded restore skips
   ordinary identity enrichment, preserving canonical file bytes.
7. Successful source activation clears the quarantine candidate and marks
   `guarded_restore_activated_off`. The port latch rejects both generic
   verified-ON and recipe-aware START enable. Emergency OFF remains
independent. Replayed deferred startup stops at the latch, and the production
charge-session tick exits before automatic decision/setpoint/enable
orchestration while the activated-off marker is present.

Any failed assessment/recheck remains quarantined with a typed `BLOCKED`
assessment. A failed canonical restore stays behind the OFF latch. The
activation code itself has no physical writer call. Ordinary unguarded restore
continues through its existing path; explicit START remains blocked while a
candidate is quarantined, and Manual behavior is unchanged.

## Remaining physical resume and P5

No method clears the OFF latch in this sprint. A later physical resume must be
a separate explicit transaction under the same lock, with a new direct Native
pre-ON snapshot and the existing assessor immediately before ON; it must retain
all existing independent safety checks. The exact matching ESPHome node,
900-second lease, callback/protection contract and corresponding Python source
must then be compiled, flashed and bench-validated before any production use.
P5 deployment/release/rollback and supervised physical acceptance remain open.

This document asserts source behavior only. It does not assert Output OFF on
hardware or `PHYSICAL PASS`.

## Verification

Synthetic behavioral and architecture coverage is in
`tests/test_d123_sprint57_guard_native_evidence.py`,
`tests/test_d070_guarded_restore_hold.py`, and
`tests/test_d123_sprint58_guarded_activation_architecture.py`. Recorded test
and full-suite results:

- Focused Guard/Native/startup/restore/START/runtime/owner batch: **121 PASS**.
- Outer canonical WSL Python 3.12 discovery with the project venv and synthetic
  `TG_TOKEN`: **2,481 tests, 3 skipped, PASS** in 105.639s.
  The first outer run exposed one real layering violation: domain
  `runtime/charge/session.py` imported the application owner-lock type. Permit
  issuance was made structurally lock-bound without importing application code;
  focused layering/activation tests then passed **27/27**, and repeated full
  discovery passed. Full log: `/tmp/d123-s58-canonical.log`.
- Whole-tree `compileall`: **PASS**.
- `git diff --check`: **PASS**.
