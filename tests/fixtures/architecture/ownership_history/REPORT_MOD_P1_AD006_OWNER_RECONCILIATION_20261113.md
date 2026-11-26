# P1-AD006 owner reconciliation report

Status: source-only diagnostic reconciliation; production/release acceptance remains **HOLD**.

## Coverage and decisions

- Baseline: AD-004 sidecar, exactly 478 unique original paths; all original evidence fields are preserved byte-for-field in this additive output.
- Reconciled working set: 480 unique rows; original 478 path set unchanged; additions: runtime/operator/off_conditions.py, runtime/charge/evidence/adopted_mix_prior_age.py.
- Architect-approved primary owners: exactly 5 and only the five below. AD-004 `proposed_owner`, evidence, mixed-responsibility, side-effect, consumer, and review fields are unchanged; every original `final_owner` notion remains empty (this schema does not add or populate one).
- Added paths have provenance `untracked_at_HEAD`, no fabricated AD-004 candidate, and `UNAPPROVED` status. Their source and caller evidence is captured in the sidecar.
- All other original rows remain unapproved. No path-derived or confidence-derived approvals are made.

| Path | Approved primary owner | Scope limit |
|---|---|---|
| `bot.py` | Composition/Configuration | Primary module owner only; no nested safety or exclusive active command authority approval. |
| `database.py` | Sessions & Persistence | Primary module owner only; no nested safety or exclusive active command authority approval. |
| `ha_history.py` | Telemetry/Evidence | Primary module owner only; no nested safety or exclusive active command authority approval. |
| `operator_dashboard.py` | UI | Primary module owner only; no nested safety or exclusive active command authority approval. |
| `runtime/physical/connectors/esp_direct.py` | Physical Execution | Adapter module only; no exclusive physical command authority, active command reachability, or bypass permission around application.ExecutionPort/Safety. |

`runtime/physical/connectors/esp_direct.py` approval classifies the adapter module only. It does not grant exclusive physical command authority, active command reachability, or bypass permission around `application.ExecutionPort` and Safety.

The false AD-004 `ChargeEngine` proposal for `database.py` is rejected by AD-006. `runtime/__init__.py` also remains unresolved; its AD-004 `ChargeEngine` proposal is rejected. This reconciliation does not approve nested safety decisions or the mixed/unresolved AD-005 batch.

## Validation limits

Inputs are local source, the immutable AD-004 sidecar, AD-004/AD-005 reports, and architect-authored AD-006. No production imports, physical reads, node access, deployment, service actions, or hardware commands are part of this tool. This report records static source/caller evidence only; it cannot establish dynamic reachability or physical behavior.
