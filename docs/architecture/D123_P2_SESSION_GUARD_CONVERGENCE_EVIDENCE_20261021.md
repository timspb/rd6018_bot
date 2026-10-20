# D123 P2 session and Guard convergence — 2026-10-21

## Scope and baseline

Source-only work started from clean `codex/d118-start-lease-repair-20261019`
HEAD `b6df3be94c36a6af755b9a99f6890b21e2a9080c`. No node104, ESP, HA,
firmware, service, deployment, GitHub, or physical Output access occurred.
No dependencies, persisted keys/schema, legacy migrations, charging policy,
lease, Manual behavior, safety, OVP/OCP, or ESP priority changed. Sprint 55C's
explicit production host configuration is retained. P4 remains closed.

## Ownership and restore order

Before this cut, `runtime.charge.persistence.restore_session` decoded and
validated the canonical JSON document, applied legacy schema normalization and
trace/session identity, reconstructed ordinary host state, and left a raw
`_session_restore_document` attribute for `ManagedChargeController` to consume.
That controller method then reconstructed DESULFATION age and SAFE_WAIT
continuations, initialized trace shadow state, performed durable enrichment,
read MAIN Guard, and restored production extension state including MIX and
COOLING-from-MIX authority.

After this cut:

1. `runtime.charge.persistence.restore_session` remains the single canonical
   document reader, schema/migration owner, identity applicator, ordinary FSM
   restore owner, and sole persistence writer. It hands accepted snapshots to
   the existing session owner as `RestoredSessionDocument`.
2. `ManagedChargeController.try_restore_session` remains the single startup
   gate and delegates accepted restore continuation to
   `runtime.charge.session_continuation_restore.finish_session_restore`.
3. The persistence owner applies the sole Guard authority boundary immediately
   after decode/retired-record validation and before any controller mutation,
   age-based deletion, continuation reconstruction, enrichment, or extension
   restore. Guard-bearing snapshots remain fail-closed.
4. Only Guard-free accepted restores reconstruct DESULFATION time and recovery
   / final SAFE_WAIT continuations, initialize shadow evidence, and perform
   durable identity enrichment. Write failure remains fail-closed.
5. Production extension restore follows Guard handling. Existing extension
   owner retains runtime signal, cooling, finish evidence, and durable MIX
   authority restoration. MIX and COOLING-from-MIX restore order is unchanged.

Custom historical restore rejection and Manual reauthorization remain in the
same startup gate. No output state is synthesized; existing callers still
provide any readback arguments, and restore does not command hardware.

## Guard admission boundary

Guard is authority-bearing data, not ordinary metadata. The canonical
`restore_session` currently detects a Guard key and returns before any host
mutation, file aging/deletion, enrichment, or extension restore. This is
intentional because the required source-only admission proof is unavailable:

- There is no owner-wide lock/reconciliation contract covering every Output ON
  route and serializing restore against enable.
- There is no required fresh direct ESP Native pre-ON readback receipt tied to
  the same session and generation, including physical Iset/OCP agreement and
  pending transaction resolution.
- A source-only change cannot establish either fact, and HA/cache or saved
  Output state cannot substitute for the live Native receipt.

Therefore Guard journal parsing/admission remains deferred and fail-closed.
The exact missing evidence is the installed owner-wide execution lock plus
current Native pre-ON reconciliation receipt and matching generation/revision
proof. No restart Output ON claim is made. This is the irreducible live/native
pre-ON boundary; no additional source-only admission cut is safe.

## Before / after couplings and gates

- `_session_restore_document` raw ad-hoc coupling: removed.
- Explicit handoff: `RestoredSessionDocument` on the existing host; persistence
  remains the sole schema owner and `finish_session_restore` is the single
  consumer/orchestrator. No second document reader, FSM, persistence writer,
  history writer, or execution owner was added.
- Authority handling: the single `GUARD_KEY` restore boundary lives in
  `runtime.charge.persistence.restore_session`; no second Guard admission check
  exists in the continuation owner. Guard state cannot flow through as ordinary
  extension metadata.
- Architecture tests enforce typed snapshot ownership, absent legacy raw
  attribute, ordered Guard/extension handling, one atomic writer, and no
  physical writer in session restore owners.

## Verification

- Focused final restore/Guard/extension/session/startup/migration batch using
  the existing Python 3.12 environment: **110 tests PASS**.
- Architecture and session continuation owner gates after the final boundary
  extraction: **11 tests PASS**.
- Python 3.12 full discovery was attempted with the existing
  `/home/home-pc/.venvs/pcp-test` environment and synthetic `TG_TOKEN`. It
  progressed through asynchronous/socket-oriented tests, then stalled without
  a final summary and was interrupted; the outer runner should execute the
  canonical full suite as specified in the request.
- Final `python3.12 -m compileall -q .`: **PASS**.
- Final `git diff --check`: **PASS**.
- Guard restore authority check exists exactly once in `runtime.charge.persistence.restore_session`, before host mutation. `session_continuation_restore` contains no second Guard admission path and no persistence import.

## Remaining D123 work

- P2 source ownership: ordinary raw snapshot seam and controller orchestration
  are converged. MAIN Guard authority admission remains externally blocked by
  the exact live/native evidence above.
- P5: release matrix, supported Python 3.10/3.11/3.12 validation, release
  acceptance, and separately authorized supervised physical acceptance remain
  open. No deployment or physical validation was performed here.
