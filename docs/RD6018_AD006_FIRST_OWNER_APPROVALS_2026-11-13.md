# RD6018 AD-006 — architect-approved primary owner assignments (2026-11-13)

Status: APPROVED primary department owner for precisely five existing production paths. This is a source-level architecture decision, NOT proof of exclusive physical authority, no approval of nested operations outside the departmental boundary, no production acceptance. Original 478-path inventory remains evidence, unchanged and with blank final_owner.

| Path | Approved primary department | Evidence and limits |
|---|---|---|
| database.py | Sessions & Persistence | aiosqlite connection, schema, record writes/reads, lifecycle import from production; preserve public DB API and data semantics |
| bot.py | Composition/Configuration | ProductionComposition, installer ordering and single application entrypoint; no new task/poll/actuator authority |
| operator_dashboard.py | UI | graph/dashboard render and callback lifecycle, HMI semantic delegation from P5-9O; preserve wrapper order and single panel |
| ha_history.py | Telemetry/Evidence | HA Recorder history DTOs, read/adaptation and continuous-ON evidence; not Native OFF proof or physical writer |
| runtime/physical/connectors/esp_direct.py | Physical Execution | infrastructure connector for ESP Native read/write methods selected via existing factory/facade; this approves adapter module classification ONLY, NOT exclusivity of physical command authority or authorization to bypass application.ExecutionPort/Safety |

Not approved at path level: 12 mixed modules and 8 unresolved as enumerated in P1-AD005 review; retain function-level/safety owner analysis. The root runtime/__init__.py is not ChargeEngine merely because its path starts runtime. database.py AD004 ChargeEngine classification is explicitly rejected. Do not automatically approve 297 high-confidence classifications or derive owners from paths/docstrings.

Coverage followup: existing canonical inventory covers 478 production paths at its snapshot; runtime/operator/off_conditions.py and runtime/charge/evidence/adopted_mix_prior_age.py are new untracked source modules used by production but absent. Additive sidecar must preserve 478 rows and add TWO clearly distinguished untracked-at-HEAD rows, resulting in a 480-entry working-set owner registry. For these two, owner is still provisional: off_conditions spans operator decision and persistence; adopted_mix_prior_age is Telemetry/Evidence candidate, not automatically approved.

Acceptance protocol: one architect-approved immutable decision record keyed by exact source path, with evidence/limits; automated tests verify five and only five approvals, no duplicate rows and 478 original rows unchanged, no unintended final_owner writes, two added gaps, full source provenance, and machine-readable sidecar. No physical/node104/deployment changes; full modularization and release remain HOLD.

Next P1-AD006: implement diagnostic approved-decisions + coverage sidecar based on this ADR, never alter original source CSV or production and never silently infer an approval.
