# D123 Sprint 29 — SAFE_WAIT continuation restore ownership

## Scope and baseline

Source-only work began at the requested exact clean HEAD
`d1f710a251b59a6c5b53af019e082e033f216112` on
`codex/d118-start-lease-repair-20261019`. No Manual, P4, device, deployment,
GitHub, recipe, threshold, lease, or actuator work was performed.

## Ownership cut

The two persisted SAFE_WAIT continuation reconstruction paths now belong to
`runtime.charge.session_continuation_restore`: recovery and final continuations
are parsed, identity/generation validated, counter/source checked, and legacy
SAFE_WAIT fields migrated there. `ManagedChargeController.try_restore_session`
retains restore ordering, runtime initialization, enrichment/failure handling,
and invokes the two owner functions. The former controller method bodies were
deleted; no forwarding wrappers remain.

This moves only continuation restore ownership. `runtime.charge.persistence`
remains the sole schema/atomic writer and retains age policy, Guard rejection,
terminal normalization, ordinary restore, and no post-restart Output ON
authority. Persisted keys/extensions, recovery/final continuation semantics,
and fail-closed guarded restore are unchanged.

Focused tests include typed continuation parity, stale identity rejection,
legacy recovery reconstruction, controller owner static guard, final/recovery
restart regressions, production restore, and guarded restore hold.

## Evidence

- Focused continuation/restore/Guard set: **49 PASS**.
- Full Python 3.12 offline discovery with synthetic
  `TG_TOKEN=123456789:d123-sprint29`: **2,423 PASS / 3 skipped**.
- `python -m compileall -q .`: PASS.
- `git diff --check`: PASS.
- Validation used the existing `/home/home-pc/rd6018-v3-deploy/.venv`
  Python 3.12 environment; no dependencies were installed.

## Next gate

Characterize a distinct ordinary session serialization ownership seam or
remaining P2 audit/session lifecycle seam before moving more code. Keep the
canonical schema and atomic writer singular. MAIN Guard restore admission
remains deferred and fail-closed. Manual, P4/P5, and physical acceptance remain
separate gates.
