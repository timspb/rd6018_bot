# AGENTS.md

This repository controls a physical RD6018 power supply and lead-acid batteries. Treat actuator changes as safety-critical.

## Production entrypoint

- Production: `python bot.py`
- `bot.py` is the small canonical composition/lifecycle entrypoint.
- `ProductionComposition` composes the canonical `runtime.production_runtime`; retired V2/legacy/shadow runtimes are absent and must not be recreated.
- Current charge, Manual, ownership, safety, execution, telemetry, persistence and UI behavior belongs to its modular production owner rather than an in-process compatibility fallback.
- Production supports Python **3.10+**. CI covers Python 3.10 / 3.11 / 3.12; Python 3.9 is not a supported deployment interpreter.

Do not add a second production entrypoint or compatibility runtime.

## Rollback controls

- Rollback is performed by reverting/deploying a previous known-good commit after the same safety prechecks used for deployment.
- There is no supported in-process legacy owner or runtime fallback.
- Existing persisted/protocol/configuration identifiers that still contain historical `v2` text are compatibility boundaries, not permission to restore V2 architecture.

Do not add environment flags or forwarding shims that resurrect superseded owners.

## Source of truth

Read these before changing control behavior:

1. `docs/V3_PROJECT_RUNBOOK.md` — current project state, merged boundaries and operational evidence.
2. `docs/V3_MODULAR_ARCHITECTURE.md` — current module/ownership contract.
3. `docs/V3_UI_MODULAR_ARCHITECTURE.md` — UI/application/transport boundary.
4. `docs/RD6018_COMPOSITION_ROOT_MODEL.md` — single production composition-root contract.
5. `docs/RD6018_FAILSAFE.md` — physical and edge fail-safe rules.
6. `README.md` — current operator/repository overview.
7. `docs/DEPLOYMENT.md` — deployment, validation and rollback runbook.
8. `docs/README.md` — documentation authority classification.
9. `docs/assistant/CHARGE_STRATEGY.md` — current charge-strategy detail where not superseded by the authorities above.
10. `docs/RECOVERY_TRACE_REPLAY.md` — trace/replay tooling.

If code and these current documents disagree, resolve the inconsistency against current `main` and the runbook; do not promote a migration-era document, old comment, deleted compatibility test or historical commit back into production authority.


## Branch hygiene

- `main` is the only long-lived canonical remote branch.
- Create short-lived `fix/*`, `feat/*`, `test/*`, `refactor/*` or `codex/*` branches from current `main` only when isolated work is needed.
- After integration, delete the remote working branch. Do **not** keep completed branches alive by fast-forwarding or force-moving them to follow `main`.
- Production authority is an exact deployed commit SHA, not a permanent release branch.
- If a retired divergent branch contains unique history worth keeping, preserve its head with an `archive/retired-YYYYMMDD/<name>` tag before deleting the branch.
- Never reset, rebase, stash or overwrite a dirty local WIP worktree merely to make its branch match `main`; preserve it and integrate it explicitly when ready.

## Control invariants

- Chemistry, intent, battery condition, program mode and actuator ownership are separate inputs.
- `Normal` is the canonical automatic chain: bounded recovery and final Mix may occur when deterministic evidence/strategy allows them.
- `Diagnostic` is the explicit no-new-automatic-HV intent.
- `Recovery` / `Conditioning` express operator purpose/context; they do not bypass evidence, recipe or safety authority.
- CV finish evidence is current-based: `Imin -> confirmed delta-I`.
- CC finish evidence is voltage-based: `Vmax -> confirmed delta-V`.
- Confirmed Mix delta starts a sticky 2-hour finish hold.
- Maximum automatic active-Mix authority is Ca/Ca 20 h / EFB 24 h / AGM 10 h. Expiry without an accepted hold is `MIX_TIMEOUT -> STOP_AND_DIAGNOSE -> verified Output OFF`, never successful Storage completion.
- Generic EFB AUTO/Recovery/Conditioning may not exceed 16.5 V. The 17.5 V outer limit is Manual/Custom authority, not an EFB entitlement.
- Independent thermal, telemetry, hardware and communication safety outrank all finish/transition logic.
- Output enable must remain transactional and fail-closed through `HassClient.safe_enable_output()` / `SafeOutputCoordinator`.
- Never reintroduce a generic PB-managed UI action that turns RD6018 ON with arbitrary pre-existing setpoints.
- `HANDS_OFF` is an explicit general-purpose PSU ownership state. Bot Pb rules and normal bot actuator writes do not own the RD while it is active.
- Normal edge-lease disarm is a verified-Output-OFF operation. Releasing an already-running managed Output to `HANDS_OFF` is a separate, explicit, session-bound ownership-transfer transaction with its own edge command and positive acknowledgement; never substitute ordinary disarm for it.
- Once durable `HANDS_OFF` has been committed, loss of the edge release acknowledgement must not silently restore `PB_MANAGED`: the release command may already have reached the edge. Preserve conservative HANDS_OFF containment and surface the uncertainty.
- Returning from `HANDS_OFF` to Pb control requires confirmed Output OFF and never silently resumes an old AUTO session.
- D061 managed live adoption and D062 `MIX_ADOPTED` are distinct authorities. D061 Adopted Manual grants no chemistry transition authority; D062 may own only an already-running high-voltage Mix after explicit battery/chemistry and prior-age confirmation.
- D062 takeover must not write Output/V/I/OVP/OCP. It reuses the D061 live-adoption edge primitive, starts Delta evidence from fresh post-adoption source reports only, and cannot re-energize Output after it becomes OFF.
- D063 prior external Mix age is conservative authority: Recorder is authoritative only with a proven uninterrupted `OFF -> ON -> ... -> current ON` edge; otherwise an explicit operator declaration is required. An already-accepted preview age is a floor that ages forward and can never be reduced by a later Recorder snapshot or Recorder outage.
- D062 chemistry budget is prior active age plus post-adoption active time. A Delta hold started before the Ca20/EFB24/AGM10 boundary may finish its sticky 2 h after the boundary; without a started hold, boundary expiry is `MIX_TIMEOUT -> verified OFF + diagnose`.
- D062 edge-command uncertainty is local to the current transaction. Failures before a new edge command may have executed are read-only and must leave the external HANDS_OFF program untouched; only an actually ambiguous edge-command invocation may enter verified-OFF containment.
- D062 software implementation is not physical validation. Do not rely on managed live takeover until the exact D061/D062 ESPHome live-adoption/900 s lease/raw-protection contract has been compiled, flashed and bench-validated on the target node.

## Deployment-only tasks

For a deployment request:

- Do not refactor code.
- Do not change `.env`, secrets, HA entity IDs, Telegram token or local runtime configuration unless explicitly requested.
- Preserve the existing service manager and service name discovered on the node.
- Back up the currently deployed working tree before replacing it.
- Check out the exact requested branch/SHA.
- Use Python 3.10+. If the current system interpreter is older or its pip is broken, do **not** repair/replace `/usr/bin/python3` in place. Provision an isolated supported interpreter/venv, validate it completely before changing the service, and change only the service interpreter path during the final handover.
- Install/update `requirements.txt` in the selected supported Python environment.
- Run:

```bash
python -m compileall -q .
python -m unittest discover -s tests -p 'test_*.py'
```

- If tests fail, do not start the new service; restore/retain the previous deployment.
- After restart, verify service state and recent logs.
- Do not start a real charge or turn RD6018 output ON as a deployment smoke test.
- Do not deploy a new edge-lease/HANDS_OFF/live-adoption contract until the exact ESPHome node/package has been compiled, flashed and bench-validated together with the matching Python version.

## Test expectations

The branch is expected to pass the complete unittest matrix on Python 3.10, 3.11 and 3.12. Do not weaken or delete safety/control tests merely to make CI green.

For ownership/watchdog changes, fake Python lease tests are not sufficient by themselves. Keep an exact ESPHome contract test and a BENCH gate for the real node because Python and edge semantics must agree.

## Scope discipline

For narrow operational tasks, make only the requested operational changes. Do not redesign charging thresholds, recipes, Telegram UX or database schema unless the task explicitly asks for it.
