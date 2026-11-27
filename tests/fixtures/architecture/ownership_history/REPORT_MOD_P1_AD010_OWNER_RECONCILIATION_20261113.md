# P1-AD010 owner reconciliation report

Status: source-only diagnostic reconciliation; physical and release status remain **HOLD**.

## Inputs and reconciliation

- Source: unchanged `.recipe-studio-local/mod_p1_owner_decisions_ad008_20261113.csv`.
- Output preserves all 480 original rows and every prior field value, then appends one row; AD010 fields are `ad010_primary_owner, ad010_decision_status, ad010_provenance`.
- Original inventory: 478 paths; AD008 additions: 2; AD010A addition: `runtime/charge/manual_session_store.py`; total working set: 481 unique paths. All three added rows retain `untracked_at_HEAD` provenance.
- Prior approvals: AD006=5 and AD008=10; new AD010 approvals=6; total=21; pending=460.
- `runtime/charge/evidence/adopted_mix_prior_age.py` is now explicitly approved while retaining its source provenance. `runtime/operator/off_conditions.py` remains unapproved. Every legacy `final_owner` remains blank.

## AD010 architect decisions

| Exact path | Approved primary department |
|---|---|
| `runtime/charge/battery.py` | Battery/Chemistry |
| `runtime/charge/chemistry.py` | Battery/Chemistry |
| `runtime/charge/decisions.py` | ChargeEngine |
| `runtime/ui/components/hmi_state.py` | UI |
| `runtime/charge/evidence/adopted_mix_prior_age.py` | Telemetry/Evidence |
| `runtime/charge/manual_session_store.py` | Sessions & Persistence |

These are narrow module classifications only. They do not claim exclusive command authority, runtime actuation authority, deployment approval, or physical acceptance. No approvals were inferred from confidence, folder, or neighboring modules.

## Validation and limits

The generator validates exact AD010 ADR rows, source existence, the exact AD006/AD008 baselines, unique 481-path coverage, untracked provenance, non-overlap, unchanged legacy rows, and blank legacy owners; invalid or conflicting input fails closed. No production, node104, HA, ESP, network, physical, service, deployment, or secret activity was performed.

Recorded local checks: `python3 -m py_compile tools/architecture/reconcile_owner_decisions_ad010.py tests/test_architecture_owner_decisions_ad010.py` — PASS; `python3 -m unittest tests.test_architecture_owner_decisions_ad010` — 7 PASS; `git diff --check` — PASS (pre-existing CRLF normalization warnings only). Tests invoke the generator directly and check deterministic bytes without subprocess capture.
