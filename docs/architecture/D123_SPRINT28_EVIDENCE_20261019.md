# D123 Sprint 28 — terminal persistence transaction contract

## Scope and baseline

Source-only work began at the requested exact clean HEAD
`02877e34861deae783e6071bee8b802b9cafc657` on
`codex/d118-start-lease-repair-20261019`. No Manual, P4, node104, ESP, HA,
deployment, GitHub, or live-output work was performed.

## Characterized contract and ownership cut

Both terminal callers now pass the shared frozen
`runtime.charge.terminal_intent.TerminalPersistenceRequest` through
`ManagedChargeController._save_session`:

- Verified SAFE_WAIT Storage completion validates the existing receipt and
  continuation first, applies the DONE edge and completion state, then issues
  one Storage/ON request with its final voltage/current/Ah snapshot.
- STOP_AND_DIAGNOSE applies its DONE edge, clearing/reset/action mutations, then
  issues one terminal/OFF request with its final voltage/current/Ah snapshot.
- The sole consumer remains `runtime.charge.persistence.save_session`. It
  establishes terminal outcome state, chooses the existing target policy,
  assembles the complete unchanged persisted document, calls
  `complete_session_document`, and makes one canonical atomic replacement.
- On atomic-writer `OSError`, save logs the failure and returns. Both callers
  retain their already-applied in-memory DONE state and actions; no rollback is
  implied. Storage authority still originates only after verified receipt
  admission.
- The canonical writer/schema and DONE restore admission/legacy terminal-OFF
  normalization remain in `runtime.charge.persistence`. No persisted keys,
  Guard/lease/recipe behavior, or physical execution moved.

The typed boundary transfers terminal outcome plus evidence snapshot intent; it
contains no document shape, serializer, restore policy, or writer. This is the
bounded seam exposed by Sprint 27's characterization gate. Broader ordinary
session serialization and restore ownership remain open.

## Evidence and validation

- Focused terminal/completion/STOP/Storage/restore/Guard/transaction/production
  set: **69 PASS**. Architecture guard plus terminal-focused recheck: **49
  PASS**.
- Full Python 3.12 offline unittest discovery with synthetic
  `TG_TOKEN=123456789:d123-sprint28`: **2,420 PASS / 3 skipped**.
- `python -m compileall -q .`: PASS.
- `git diff --check`: PASS.

## Next gate

Continue only with the separately scoped ordinary session serialization or
restore ownership characterization. Keep `runtime.charge.persistence` as the
single schema/atomic writer. P2 Guard restore admission remains deferred and
fail-closed; Manual, P4/P5, and physical acceptance remain separate gates.
