# AD157 — restore/startup acceptance

2026-11-17. Working branch `feature/main-mix-countdown-display`; baseline HEAD before this work: `3c692554074b27805419a9b0767133a1c8d78150`.

## Result

**PASS — 121/121 Windows tests** in the focused restore/startup cohort, using the repository's existing Windows `.venv`. The dedicated AD155 cancellation-at-first-post-restore-await test also passed independently.

The cohort covered:

- restore finalization contract and use case;
- restore continuation failures;
- AD155 lifecycle containment/cancellation;
- recovery quarantine and atomic auto-restore admission;
- session recovery guard;
- startup recovery;
- START_PENDING persistence/recovery/service/adapter tests.

## Production correction

In `runtime/charge/persistence.py`, after applying the restore timeline, the persisted terminal projection is now included in the existing terminal-document normalization decision:

```python
restored_terminal = timeline.restored_terminal
normalize_done_document = bool(normalize_done_document or restored_terminal)
```

This closes the expired MIX → DONE path: terminal state from the projection now reaches the existing finalizer/normalizer and canonical compare-and-replace write. The existing snapshot/preimage/CAS boundary remains in place. `runtime/charge/restore_projection.py` was not modified (HOLD).

## Test corrections and contracts retained

- Adapter-level `_save_session` returns the exact persistence result, including COMMITTED and OUTCOME_UNCERTAIN outcomes.
- The expired-MIX finalization tests verify normalization and persistence ordering; failed persistence does not turn stage tracking on.
- Startup recovery tests now inspect the current quarantine helper/lifecycle path rather than retired AST structure.
- AD155 cancellation fixture uses the actual production host's `STAGE_SAFE_WAIT` and `STAGE_MAIN` constants. It reaches the real ExecutionPort, injects `CancelledError` at `program_voltage`, and verifies re-raise, latched quarantine, and no background-control start.
- The actual ExecutionPort factory/guard-owner-lock binding is retained; no production lifecycle or guard semantics were weakened.

## Verification and environment

- Windows `.venv`: focused AD155 cancellation test PASS.
- Windows `.venv`: complete focused cohort PASS, 121/121.
- `git diff --check`: no whitespace errors; Git emitted only the existing LF→CRLF working-copy warning for `runtime/charge/persistence.py`.
- WSL Codex test execution was not available because `python-dotenv` is absent in that environment. No dependency was installed and no environment was altered.
- No hardware, node104, ESP, HA, or production deployment was performed.

## Repository boundary

No stage, commit, push, reset, clean, stash, or checkout was performed. Branch and HEAD remain as above; existing unrelated dirty/untracked work was preserved. This acceptance note records test evidence only and does not claim a committed release or deployment.

## Next step

Keep this acceptance scoped to the restore/startup cohort. Before any broader release or physical operation, run the project's remaining acceptance gates and review the full worktree diff against its existing dirty baseline.
