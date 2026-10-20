# D123 Sprint 27 — terminal persistence ownership assessment

## Scope and baseline

Assessment from exact clean HEAD
`7f5e334d2d657b1c22528026fd7f1dafece162c8` on
`codex/d118-start-lease-repair-20261019`. The requested P3 area was broader
terminal session-persistence ownership and Storage/DONE integration after
Sprint 26. This was source-only. No live system, device, deployment, recipe,
threshold, lease, Guard, Manual path, or P4 work was touched.

## Ownership finding and blocker

`runtime.charge.persistence.save_session` owns the canonical session schema and
atomic write. It materializes terminal metadata, preserves known measurements,
chooses Storage targets only for the explicit verified Storage intent, and
calls `complete_session_document` before the single atomic replacement. The
same module admits only explicit persisted Storage/DONE intent for automatic
enable and normalizes ambiguous legacy DONE documents to terminal/OFF.

The verified Storage path reaches persistence only after the existing
session-bound verified-enable receipt; its effect applies the DONE stage edge
before the canonical save. `STOP_AND_DIAGNOSE` is a second terminal caller and
uses the same save boundary with terminal/OFF fallback. A partial extraction of
DONE serialization would create a second schema authority or change the
receipt -> stage edge -> save order. Moving generic serialization and restore
normalization together would be a broader persistence rewrite without a
bounded, independently parity-checkable P3 cut. No safe ownership cut was
identified, so no source ownership was moved or deleted and no new abstraction
was introduced.

## Validation

- Focused terminal/Storage/restore/failure suites: **35 passed** across
  `test_final_safe_wait_output_transaction`, `test_done_storage_restore_contract`,
  `test_restore_terminal_guard`, `test_d123_p3_stop_diagnose_effect`,
  `test_session_atomic_guard_binding`, and `test_d123_p3_residual_terminal`.
- Full Python 3.12 offline unittest discovery with
  `TG_TOKEN=123456789:d123-sprint27`: **2,416 passed, 3 skipped**.
- `/home/home-pc/rd6018-v3-deploy/.venv/bin/python -m compileall -q .`: PASS.
- `git diff --check`: PASS.

## Next gate

Characterize a transaction-shaped terminal persistence port shared by both
Storage completion and STOP_AND_DIAGNOSE, with exact action/state parity,
injected canonical-writer failure, schema parity, DONE restore admission, and
legacy terminal/OFF normalization across restart. Preserve one canonical atomic
writer and the receipt -> stage edge -> save ordering. Continue P3 only if those
tests define a seam that transfers real terminal snapshot authority without
splitting the generic session schema owner. Otherwise retain canonical
persistence ownership. P2 Guard restore admission remains fail-closed/deferred;
P4 has not started.
