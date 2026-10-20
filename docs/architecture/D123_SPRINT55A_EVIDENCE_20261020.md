# D123 Sprint 55A evidence — 2026-10-20

## Scope and baseline

Source-only continuation on branch `codex/d118-start-lease-repair-20261019`,
starting from exact clean HEAD `66534932098969dbf251e29934e3388699683c9c`.
No production node, ESP, HA, firmware, service, deployment, GitHub, or physical
Output action was used. No dependencies or policy thresholds changed.

Required pre-change inputs were read: the D123 convergence checklist, owner map,
Sprint 54 evidence, and `/tmp/d123-s55.log`. Sprint 55 had stopped without edits
after finding the AUTO, Diagnostic, and durable MIX active-time subclass behavior.
This sprint preserved those authorities and made the presentation and diagnostic
snapshot cuts that can be safely moved without changing their state ownership.

## Exact subclass member changes

| Class | Before | After |
|---|---|---|
| `AutoStrategyProductionChargeController` | `_OPERATOR_REASON_TEXT` mapping; `_get_stage_max_hours`; `_mix_display_elapsed_s`; `get_timers`; `_session_rules_summary`; `get_ai_stage_snapshot` | No declared methods or mapping; class remains as a compatibility name over `ProductionChargeController` |
| `ProductionChargeController` | `_OPERATOR_REASON_TEXT` class mapping, plus no declared method overrides | Mapping removed; remains the empty production marker subclass |
| `DiagnosticProductionChargeController` | `__init__`, `battery_fault_assessment`, `update_diagnostic_context`, `_refresh_stored_diagnostics`, `_update_live_diagnostic_evidence`, `diagnostic_snapshot`, `_diagnostic_hv_veto` | `diagnostic_snapshot` removed; other six declarations retained |
| `MixActiveAuthorityMixin` | `_enter_mix`; `try_restore_session` | Unchanged; both durable MIX authority overrides remain |

AUTO presentation functions now operate on the same host in
`application.production_session_extensions`: `auto_stage_max_hours`,
`auto_mix_elapsed_s`, `auto_timers`, `auto_session_rules_summary`,
`auto_ai_stage_snapshot`, and `auto_operator_reason_text`. The base host invokes
them while retaining its original defaults for a standalone host without
production extension state. Durable MIX elapsed display still uses the active
authority snapshot for the matching session, falling back to stage elapsed time
as before. Existing timer keys, string formatting, EFB snapshot values, and
operator text mappings are preserved. Stage-limit callers remain the existing
restore/lifecycle paths; UI/runtime timer and AI consumers are unchanged; the
notification caller remains `application.charge_session_tick`.

Diagnostic snapshot field projection now lives in
`runtime.charge.diagnostics.diagnostic_assessment_snapshot`; the existing
`application.charge_stage_tick` invokes it against the same
`battery_fault_assessment` object. Assessment construction/mutation was not
copied or moved. Stored SG refresh is still awaited by
`application.charge_session_tick` through `_refresh_stored_diagnostics`. Live
bank-fault evidence still enters through `_update_live_diagnostic_evidence` in
`application.charge_stage_tick`. `_diagnostic_hv_veto` remains applied before
stage transition effect application through `decision_veto`.

## Durable MIX authority and restore order characterization

`MixActiveAuthorityMixin._enter_mix` first delegates to the existing MIX entry
implementation, then begins the durable active-time record using the session ID
from `recovery_trace_context`, initially inactive. Stage-entry dispatch reaches
this method through the existing diagnostic host MRO.

`MixActiveAuthorityMixin.try_restore_session` first calls the canonical base
restore. That canonical restore retains persistence restore, fail-closed MAIN
Guard handling/admission, and production extension reconstruction in the
Sprint 54 order. Only after success does the mixin inspect whether the
restored stage is MIX or COOLING whose saved `source_stage` is MIX. It loads the
durable active-time record for that session. A missing/invalid/mismatched record
sets the host to DONE, clears finish timer and restored targets, and rejects the
restore. Production runtime restore reaches this MRO method. Moving this logic
requires preserving the Guard-before-MIX ordering and the fail-closed rejection.

## Verification

Focused source verification used the existing Python 3.12 environment at
`/home/home-pc/rd6018-v3-deploy/.venv/bin/python` with synthetic
`TG_TOKEN=123456789:d123-sprint55a` and `PYTHONPATH=tests`:

- AUTO strategy/presentation, Diagnostic controller and snapshot ownership,
  durable MIX timeout, session restore, production extension, production
  controller, startup authority, Manual runtime, START transaction, MAIN Guard
  admission, cooling contract, recovery resume transaction, and final
  SAFE_WAIT transaction suites: **95 tests, PASS**.
- `python -m compileall -q .`: **PASS**.
- `git diff --check`: **PASS** after removing an extra trailing blank line.
- Full `python -m unittest discover -s tests -p 'test_*.py'` was attempted under
  Python 3.12 with the same synthetic token. It emitted progress for roughly two
  minutes, showed one error marker, then stopped producing output. It was
  interrupted; there was no final unittest summary, so full discovery is
  **incomplete and not claimed as PASS**. This matches the sandbox/socket
  limitation reported by the prior Sprint 55 log. Leave full canonical discovery
  to the outer runner.

The first corrected focused command lacked `PYTHONPATH=tests`, causing a test
helper import error. The corrected command above passed all 95 tests. An earlier
invocation also included three guessed, nonexistent module names; those import
errors were not product test failures.

## Remaining cuts and gates

- **P4:** Remove the remaining production marker inheritance only after moving
  the diagnostic assessment state/update, stored SG refresh, live evidence,
  pre-apply HV veto, and durable MIX begin/restore behavior onto existing
  application/runtime owners over the same host. Specific next cut: move the
  diagnostic assessment context/update and stored SG/live evidence projection,
  preserve the existing pre-apply veto call order, and leave the Mix mixin intact
  until tests prove its caller/order migration. Then migrate durable MIX entry
  and restore as a separate P4 slice with timeout, restore, cooling and Guard
  regressions. No new facade/controller/framework/state host.
- **P2:** MAIN Guard restore admission and remaining raw canonical session
  document/audit lifecycle ownership remain deferred. Guard restore remains
  fail-closed and must precede extension/MIX restore effects.
- **P5:** Full Python-version matrix, canonical full discovery, exact source
  release gates and supervised physical acceptance remain open. This sprint
  provides no physical acceptance and authorizes no deployment.

Single FSM/session host, canonical persistence writer, and physical execution
owner remain unchanged. The 900-second lease, safety, recipes, OVP/OCP,
ESP-priority, Manual, and actuator transaction behavior were outside this cut.
