# P1-AD067 — Restore finalization owner decision and projection HOLD
Date: 2026-11-15
Status: ACCEPTED for one owner; NO FILE-LEVEL APPROVAL for the mixed projection module.

## Decision

- `runtime/charge/restore_finalization.py` → **Application**.
- `runtime/charge/restore_projection.py` → **NO FILE-LEVEL APPROVAL / HOLD**.

## Why finalization is Application

`finalize_restored_session` coordinates the accepted restore's final application sequence: resets/sets enrichment and stage-tracking flags, invokes the terminal-document normalizer callback, captures the immutable `RestoredSessionDocument` snapshot, and for a restored terminal state invokes the host's existing save operation before enabling stage tracking. The order and partial-mutation behavior are observable contracts.

It does not own document loading/acceptance, the session schema, durable storage, restore admission, charge-stage policy, Safety admission, Output or physical execution. Its only production import/call is from `runtime/charge/persistence.py` (import near line 43; invocation near lines 873–881). The single caller is not sufficient reason to move the orchestration back into the persistence monolith.

## Why restore_projection remains unapproved

The module contains two distinct pure projections:
- `project_restore_scalars`: normalization/defaulting/clamping of persisted scalar session fields — Sessions & Persistence responsibility.
- `project_restore_stage_timeline`: continuation/timer and terminal-stage decision for restored Desulfation/MIX timelines, including expired MIX → DONE — stage-transition responsibility.

Both are side-effect free and called only by the existing `restore_session` path in `persistence.py` (scalar projection near lines 655–659; timeline projection near lines 781–801). However, the two functions encode different decisions. The current source evidence does not justify one file-level owner or an immediate move into `main_authority.py`, which is specifically the canonical MAIN transition owner. Do not split, duplicate, or relocate this code until a separate owner decision identifies the correct existing stage owner for restore-time timeline continuation.

## Independent audit and tests

Read-only Codex audit:
- exact source, production callers, tests, AD012 inventory and AD014 decision evidence inspected;
- Codex CLI GPT-6 Luna, read-only, exit code 0;
- report: `/tmp/RD6018_P1_AD067_RESTORE_OWNER_AUDIT_20261115.md`;
- R7.2 completion notification event `586a6a1133694480a8dfa5ba338795f0` accepted for this chat route; route inspector still reports `last_ack=null`, so host ACK is not claimed.

Independent Windows project `.venv` tests:
- projection/timeline/finalization cohort: **18 passed, 10 subtests passed**;
- finalization contract/continuation/use-case cohort: **23 passed, 6 subtests passed**.

No source/test/CSV change was made for AD067.

## Scope

This is a source-backed owner decision only. No restore algorithm, timer, stage rule, session format, persistence write, Safety rule, Output, lease, ExecutionPort, physical adapter, firmware, HA/ESP, device or deployment changed. Existing WIP is preserved; release remains HOLD.
