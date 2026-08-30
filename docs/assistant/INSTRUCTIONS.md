# Assistant / maintainer instructions

For V2 charging/recovery work, do not reconstruct intended behavior from chat history or from legacy implementation details when the durable docs answer it.

## Read order before changing strategy

1. `V2_DECISION_LOG.md` — accepted/rejected behavior.
2. `V2_OPEN_QUESTIONS.md` — only genuinely unresolved strategy/calibration questions.
3. `CHARGE_STRATEGY.md` — compact production reference.
4. `PB_RECOVERY_V2.md` — architecture/authority boundaries.
5. `V1_BEHAVIORAL_AUDIT.md` — factual V1 behavior when compatibility matters.
6. `HISTORY.md` — rationale/history only.

If code disagrees with an accepted Decision Log entry, treat it as an implementation defect unless a newer explicit decision supersedes the entry.

## Safety/authority rules

- Hard physical safety/readback/watchdog boundaries outrank operator program and chemistry strategy.
- `battery_voltage` is the chemistry voltage source; RD output voltage is hardware/output monitoring.
- Vin is PSU-health telemetry, not Pb chemistry authority.
- BAT_MODE is observation, not software permission.
- Manual V/I are operator-owned inside the 17.5V/12A outer envelope; OVP/OCP are derived and non-overridable.
- Optional Manual `battery_id` is history/diagnostic identity only; never import AUTO chemistry/C-rate targets from it.
- Persisted active Manual always restores `INTERRUPTED`; only explicit fresh operator re-authorization may energize again.
- Durable diagnostic evidence may survive restart; in-flight diagnostic authority/actions do not. Never resume a current probe mid-step or preserve expert-HV authorization across process restart.
- Derived `BLOCK_AUTOMATIC_HV` must be recomputed from evidence; do not persist it as a permission token.
- AI remains advisory only.

## Change discipline

When changing behavior:
- add/update a numbered Decision Log item;
- remove resolved Open Questions;
- update Charge Strategy when operator-visible behavior changes;
- add deterministic regression tests;
- keep `main` untouched while PR #2 is Draft;
- do not mark PR ready or merge until physical/on-device validation is complete and explicitly approved.

## Remaining non-software-only work

Current open set is intentionally concentrated in calibration/manufacturer/physical validation:
- Q004/Q013 fault scoring against real traces;
- Q005/Q014 controlled probe + RD6018 measurement calibration;
- Q011 expert EFB 17.2–17.5 workflow;
- Q012 SG correction/applicability/prompt policy;
- Q015 final physical/main-merge validation.

Do not invent numeric thresholds for these merely to close the list.
