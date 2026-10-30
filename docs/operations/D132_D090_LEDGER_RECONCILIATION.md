# D132 — node104 D090 deployment ledger reconciliation (read-only evidence)

## Observed state, 2026-10-31

This note describes evidence, **not** an authorized cutover or a committed deployment.

- `rd6018-bot.service`: active, MainPID `162141`, NRestarts `0`.
- Durable recovery journal: `state=retired`, `quarantined=false`; incident `b6b90c17-02ee-44c3-8c78-6eafe8243441`; physical OFF evidence `execution-port-off:1793374858315444915`.
- Durable session file: `stage=RETIRED`, session `e18eb85b81b44aeabd1eb7b29443594c`; the same OFF evidence.
- D063 observer service active; `no_eligible_safe_wait` is expected for RETIRED rather than manufacturing a SAFE_WAIT session.
- `/opt/services/rd6018-bot/D090_TRANSACTION.json`: transaction `818df047a6e64a22905d6da900162a86`, `phase=STARTED`, source `930239c670899e14ccb09154d99baf77df90da10`; `candidate_inventory` absent.
- `.deploy_sha`: `58321a866dd68195bf8264d1d9ebe7c18a60748f` — historical preimage marker, **not** proof of the currently installed source.
- Backup `backups/d090-818df047a6e64a22905d6da900162a86`: all 13,908 entries match the journal's backup inventory; `.env`, `.deploy_sha`, and `service.unit` digests match baseline.
- Live `state/` differs from the preimage inventory (2,506 versus 2,505 entries). Never restore preimage `state/` onto the retired session. Do not treat the existing `STARTED` transaction as `COMMITTED`.

## Preflight repair already deployed locally

The node-local `/opt/services/rd6018-bot/d090/node104_d090_transaction.py` was patched to compare backup structure, full inventory, baseline digests, and current environment/unit/state/marker **before** invoking `service.stop()`. An isolated offline test confirms a missing backup is rejected with no stop and no journal mutation. Full backup inventory comparison returned true. The patch is **node-local** until source ownership and synchronization into the canonical repository are established. It has not been validated by a full end-to-end release/rollback suite.

## Closure criteria (no implicit permission to act)

1. Identify and version the owner of node-local D090 CLI and compare to canonical sources byte-for-byte. Preserve a copy and hashes of the currently running app, actual unit, environment digest (never environment contents), state schema, and D090 journal.
2. Add exhaustive negative cases to the same D090 transaction owner's offline suite: incomplete journal, bad full inventory, altered baseline and live state, wrong marker, missing backup components. Verify `stop_calls==0`, no production mutation.
3. Represent the old `STARTED` record as a **superseded, historical transaction** only through a documented owner-supported transition with an independently verifiable audit trail. Never edit its phase to `COMMITTED`, reconstruct an absent candidate inventory, delete the backup, or quietly rewrite the marker.
4. Introduce a new independent deployment baseline bound to **actual installed bytes** and the approved release artifact, with explicit state preservation. Verify runtime process identity and absence of accidental Output ON, setpoint writes, OVP/OCP changes, or lease-ttl changes.
5. Only after the owner tests and live read-only acceptance pass may normal installation/update/DR be considered reopened.

The safety lease remains 900 seconds. This reconciliation work must never start charging, turn Output ON, modify charge protections, stop the bot to test recovery, or roll back retired session state.
