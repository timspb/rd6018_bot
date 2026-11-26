# RD6018 AD-010 — Third primary owner approvals (2026-11-13)
Status: Architect APPROVED exactly six primary MODULE owners, source-only. Existing AD006 five + AD008 ten remain unchanged. No physical executor exclusivity or deployment acceptance.

| Path | Owner |
|---|---|
| runtime/charge/battery.py | Battery/Chemistry |
| runtime/charge/chemistry.py | Battery/Chemistry |
| runtime/charge/decisions.py | ChargeEngine |
| runtime/charge/manual_session_store.py | Sessions & Persistence |
| runtime/ui/components/hmi_state.py | UI |
| runtime/charge/evidence/adopted_mix_prior_age.py | Telemetry/Evidence |

Evidence: P1-AD009 source report and architect independent review on HEAD 3c69255. These assignments preserve existing source/public API and denote narrow module responsibilities, not actuation authority.
AD010 reconciliation must preserve AD008 480-row working set, 15 prior approvals, the original 478 paths and both added-path provenance fields, and add precisely these six approvals: 21 approved, 459 unapproved. Keep original final_owner blank. Newly approved adopted_mix_prior_age.py retains its untracked_at_HEAD provenance. runtime/operator/off_conditions.py remains UNAPPROVED because it combines operator stop rules with persistence. SafeOutputCoordinator, other 18 AD009 entries, physical command chain and release remain unapproved/HOLD.
Codex is authorized only to create new diagnostic reconciler/test/sidecar/report files named in P1-AD010 task; no production, original inventories, old ADRs, node104 or hardware changes.