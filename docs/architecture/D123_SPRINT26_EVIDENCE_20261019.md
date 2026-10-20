# D123 Sprint 26 — verified Storage terminal persistence intent

## Scope and baseline

Source-only cut from exact clean HEAD
`33382b6edd424876738896d81e3a48c58f2b7338` on
`codex/d118-start-lease-repair-20261019`. The verified final SAFE_WAIT to DONE
commit already owned the terminal save call, but communicated Storage
completion to canonical persistence through mutable `_done_transition_source_stage`
host state. Sprint 26 replaces that implicit marker with an explicit
`verified_storage_completion` argument at the canonical save boundary. The
frozen `FinalSafeWaitCompletionEffect` applicator is the only production caller
that sets it true.

Canonical persistence remains the sole schema/atomic-write owner. Persisted
keys and values, DONE restore admission, conservative terminal fallback,
session-bound receipt validation, execution-port transaction ordering and
fail-closed behavior are unchanged. No stage algorithms, physical setters,
lease, Guard, recipes, thresholds, hardware, HA, deployment or GitHub paths
were touched. No P4 ownership migration was started.

## Ownership change and guards

- Removed `_done_transition_source_stage` from controller state initialization,
  completion apply/cleanup, and persistence inference.
- Added an explicit, default-false `verified_storage_completion` keyword across
  controller and production-controller save boundary into `save_session`.
- Updated Storage persistence characterization to supply the explicit verified
  intent and added a static guard that the old marker cannot return.
- No new controller, framework, facade, or persistence writer was introduced.

## Validation

- Focused Python 3.12: **21 passed** across verified completion, Storage
  persistence/restore, restore contract and terminal guard suites.
- Full offline Python 3.12 discovery with synthetic
  `TG_TOKEN=123456789:d123-sprint26`: **2,416 passed, 3 skipped**.
- `/home/home-pc/rd6018-v3-deploy/.venv/bin/python -m compileall -q .`: PASS.
- `git diff --check`: PASS.

## Remaining gates

Broader terminal serialization ownership, Storage/DONE and Manual integration,
remaining typed stage/application orchestration, and P4 removal of production
`ManagedChargeController` ownership remain unchecked. P2 MAIN Guard restore
admission remains deferred and fail-closed. No physical acceptance is claimed.
