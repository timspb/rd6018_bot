# D144 — legacy D090 STARTED journal convergence

## Finding

The reported node104 journal is a schema-1 `STARTED` transaction with the
legacy key set and no `candidate_inventory`. The reported pins are
transaction `818df047a6e64a22905d6da900162a86`, candidate source
`930239c670899e14ccb09154d99baf77df90da10`, and old source
`58321a866dd68195bf8264d1d9ebe7c18a60748f`. These are task-supplied values;
this source-only sprint did not read node104.

Inspection of commit `930239c` shows the cause. `prepare()` returned the full
candidate inventory in memory. `activate()` then created the first journal
record without copying that field. `_phase()` rewrote the same dictionary at
each step, so reaching `STARTED` did not add it. D143 correctly requires the
field, because the source SHA does not prove the generated venv's exact bytes.

The app inventory may be independently reconstructed from a verified source
archive/Git tree only when its exact manifest and digest are authenticated and
the installed app matches that inventory. The venv must also match an
independently preserved, cryptographically authenticated candidate-venv
inventory. A marker, requirements file, current installed venv, or D090 backup
of the *old* venv is not proof of the candidate venv. This checkout has no
preserved candidate venv artifact tied to this transaction, so a complete
candidate inventory cannot be derived here.

## Implemented behavior

`reconcile_started()` now reports the legacy missing-inventory case explicitly
and refuses before proof acquisition or any marker/journal/service mutation.
It does not backfill, infer, or rewrite journal evidence. Current journals
with complete inventories continue through the existing exact checks.

D090 `edge_boot_quarantine` represents the hardware ESP boot-quarantine flag.
It is separate from D084's process-local application `SessionRecoveryGuard`.
Passing a hardware lease/quarantine proof does not prove that the D084 guard is
clear, and D090 recovery/reconciliation does not rearm or clear that guard.
Electrical OFF, zero U/I, lease and hardware protection checks remain required.

## Safe migration procedure

1. Preserve the original journal and transaction backup byte-for-byte. Do not
   edit the journal, deployment marker, service files, or installed tree to
   make reconciliation pass.
2. Keep the current service and quarantine state unchanged while gathering
   artifacts. Obtain the exact staged archive/release manifest and exact
   candidate venv artifact from storage independent of the installed node
   trees. Verify their immutable digests against reviewed release pins.
3. Produce the inventory using the existing D090 inventory format and compare
   it against the live installed app and venv. The process must be independently
   reviewed, read-only, and transaction-bound. A Git app-tree match without a
   candidate-venv match is insufficient.
4. If either artifact or digest is unavailable, leave the STARTED transaction
   unresolved. Do not claim reconciliation PASS. Use only existing D090
   `recover` after its ordinary node identity, complete backup, and fresh
   direct Native/independent proof gates are available; that path restores the
   old preimage and is distinct from accepting the candidate.
5. Treat D084 software quarantine through its existing operator/safety owner.
   Do not infer its state from ESP hardware quarantine, and do not use D090
   reconciliation or recovery as a quarantine-clear operation.

No node104, ESP, HA, service, journal, marker, or backup operation was
performed for D144. The local read-only D106 collector could not access the
system bus (`systemctl`: `Operation not permitted`) before attempting its
Native subscription; the live physical status for this sprint is **ESP ACCESS
BLOCKED**. User-supplied current-state notes are not substituted for a fresh
native read.

## Validation

The regression test creates the reported legacy shape and verifies explicit
fail-closed behavior: journal and marker bytes remain unchanged, the proof
provider is not called, and the fake service is neither stopped nor started.
Existing reconciliation success and refusal tests cover the complete-inventory
path. This is source-only software evidence, not node or hardware validation.
