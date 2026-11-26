# P1-AD008 owner reconciliation report

Status: source-only diagnostic reconciliation; release remains **HOLD**.

## Inputs and reconciliation

- Source: unchanged `.recipe-studio-local/mod_p1_owner_decisions_ad006_20261113.csv`.
- Output: additive AD008 sidecar with all AD006 columns and row values retained, plus only `AD008_approved_primary_owner, AD008_approval_status, AD008_decision_provenance`.
- Coverage: 480 unique paths. Original AD006 approval records: 5; new AD008 approval records: 10; total approved: 15; pending: 465.
- Every `final_owner` remains empty. The two additive working-set paths remain unapproved.

## AD008 architect decisions

| Exact path | Approved primary department |
|---|---|
| `runtime/charge/strategy/desulfation_variables.py` | ChargeEngine |
| `runtime/telemetry/snapshot.py` | Telemetry/Evidence |
| `runtime/ui/components/journal_filter.py` | UI |
| `runtime/ui/components/main_stage_progress.py` | UI |
| `runtime/ui/components/mix_stage_progress.py` | UI |
| `runtime/ui/components/stage_duration.py` | UI |
| `runtime/ui/labels/operator_actions.py` | UI |
| `runtime/ui/screens/analysis.py` | UI |
| `runtime/ui/screens/help.py` | UI |
| `runtime/ui/screens/stats.py` | UI |

These are narrow primary module classifications only. They do not claim exclusive command authority, active runtime reachability, safety ownership, or permission to alter production behavior. No ownership was inferred from folder, confidence, or neighboring modules.

## Validation and limits

The generator validates exact owner strings against the AD008 ADR, verifies each source path exists, checks the AD006 five-approval baseline and empty `final_owner` values, and fails closed on missing paths or conflicts. This is static diagnostic evidence only; no production, node104, HA, ESP, physical, network, deployment, or release validation was performed.

Recorded local checks: `python3 -m py_compile tools/architecture/reconcile_owner_decisions_ad008.py tests/test_architecture_owner_decisions_ad008.py` — PASS; `pytest -q tests/test_architecture_owner_decisions_ad008.py` — 4 passed; `git diff --check` — PASS. Output determinism and field preservation are covered by those four targeted tests.
