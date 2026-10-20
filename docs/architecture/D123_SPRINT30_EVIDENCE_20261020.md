# D123 Sprint 30 — ordinary restore snapshot seam audit

## Scope and baseline

Source-only audit began at exact clean HEAD
`6097ce89ad9837b94766a3d0c9478f08e60d8845` on
`codex/d118-start-lease-repair-20261019`. No MAIN Guard admission, Manual, P4,
live systems, deployment, GitHub, recipe, threshold, lease, or actuator work was
performed.

## Seam examined and blocker

The ordinary restore handoff is `host._session_restore_document`, assigned by
`runtime.charge.persistence.restore_session` from its accepted canonical parsed
document. It is read by two active callers:

- `ManagedChargeController.try_restore_session` copies it to `trace_document`
  and uses it for DESULFATION stage-clock restoration, recovery/final SAFE_WAIT
  continuation restore, and durable identity enrichment.
- `ProductionChargeController.try_restore_session` copies it to `document`,
  restores persisted Guard with `main_guard_session.read_guard`, and restores
  MIX finish and runtime signal state.

The raw document is necessary across these consumers because it preserves the
canonical Guard journal and extension keys alongside ordinary persisted state.
A narrow typed projection would either omit authority/evidence needed by the
existing Guard consumer or expand into a second schema representation. Moving
the consumer sequence into persistence would cross the explicitly deferred
MAIN Guard restore admission boundary. No safe bounded implementation cut was
identified; the audit is recorded as a blocker rather than introducing another
serializer or changing restore ordering. `runtime.charge.persistence` remains
the sole canonical schema and atomic writer.

Added `tests/test_d123_sprint30_session_seam_blocker.py` as a static ownership
guard for the exact shared handoff, Guard consumer, and canonical schema/atomic
completion path. Persisted keys/extensions, terminal intent, Guard journal
semantics, restore age, and fail-closed behavior are unchanged.

## Evidence

- Focused ownership guard: **2 PASS**.
- Full Python 3.12 offline discovery with synthetic
  `TG_TOKEN=123456789:d123-sprint30`: **2,425 PASS / 3 skipped**.
- `python -m compileall -q .`: PASS.
- `git diff --check`: PASS.

The full suite retains parity, restore-age, Guard hold, atomic-write failure,
terminal-intent, and fail-closed regression coverage; the focused Sprint 30
test adds static caller/owner assertions. Python environment:
`/home/home-pc/rd6018-v3-deploy/.venv` (Python 3.12); no dependency install.

## Next gate

Inspect a remaining P2 audit/session lifecycle seam only if it can move without
crossing MAIN Guard restore admission or creating a second schema/serializer.
Otherwise defer until Guard admission work is explicitly in scope. Manual, P4,
live systems, deployment, recipes, thresholds, lease and physical acceptance
remain separate gates.
