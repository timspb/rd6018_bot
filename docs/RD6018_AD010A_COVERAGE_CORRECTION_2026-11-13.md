# RD6018 AD-010A — Correct working-set coverage, 2026-11-13

Architect amendment to AD-010; its SIX approved primary owner mappings stay EXACTLY unchanged.

Verified source fact: runtime/charge/manual_session_store.py is an existing active Manual JSON storage module in the dirty checkout, but git reports it UNTRACKED at HEAD 3c69255 and it is absent from both the historical 478-path inventory and the AD008 480-row working set. The P1-AD010 original 480-row result contract was therefore arithmetically impossible. Codex correctly failed closed.

MANDATORY reconciliation: preserve every AD008 original 480 path and all field values exactly; APPEND precisely this one new source module as an additive 481st row, mark inventory_provenance=untracked_at_HEAD and existing_candidate=NO_AD004_CANDIDATE (no fabricated historical evidence), include its exact real source/caller evidence, and record its architect-approved AD010 primary department Sessions & Persistence with AD010 decision provenance. Preserve other two additional paths and their provenance: runtime/operator/off_conditions.py remains UNAPPROVED, runtime/charge/evidence/adopted_mix_prior_age.py receives its AD010 approval as Telemetry/Evidence. New totals: **481 unique working-set production paths; AD006=5, AD008=10, AD010=6, TOTAL APPROVED 21, UNAPPROVED 460**. Old 478 source inventory and AD004/AD006/AD008 sidecars shall NOT be edited; final_owner remains blank for every path.

Prior AD010 statement '480 total/459 unapproved' is superseded by this specific corrective ADR. This is source-only owner inventory maintenance, not Git staging, hardware validation or permission to deploy. No physical/node104/HA/ESP work. Next independent Windows check and mandatory four-doc checkpoint after acceptance.
