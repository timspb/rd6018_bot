# AGENTS.md

This repository controls a physical RD6018 power supply and lead-acid batteries. Treat actuator changes as safety-critical.

## Production entrypoint

- Production: `python bot.py`
- `bot.py` is intentionally a small V2 entrypoint.
- The preserved previous Telegram/HA runtime is `bot_legacy.py`.
- Production controller: `DiagnosticProductionChargeControllerV2` from `diagnostic_controller.py`.
- `ProductionManualSessionManager` is the managed Manual authority.
- `RdControlModeManager` is the outer RD6018 ownership boundary (`PB_MANAGED` / `HANDS_OFF`).

Do not replace the production entrypoint with `bot_legacy.py` during a normal deployment.

## Rollback controls

These environment flags are supported independently:

- `V2_UI=0` — old Telegram presentation, current actuator authority unchanged.
- `V2_AUTHORITATIVE=0` — legacy Main/Mix authority, V2 UI may remain enabled.
- Full rollback: `V2_UI=0 V2_AUTHORITATIVE=0 python bot.py`.
- Emergency preserved runtime: `V2_AUTHORITATIVE=0 python bot_legacy.py`.

Do not add either rollback flag during a normal V2 deployment unless explicitly requested.

## Source of truth

Read these before changing control behavior:

1. `docs/assistant/V2_DECISION_LOG.md` — durable accepted/implemented decisions.
2. `docs/assistant/V2_OPEN_QUESTIONS.md` — genuinely unresolved strategy/calibration questions.
3. `docs/assistant/CHARGE_STRATEGY.md` — current production strategy.
4. `docs/assistant/PB_RECOVERY_V2.md` — V2 architecture and invariants.
5. `docs/assistant/RD_HANDS_OFF_MODE.md` — general-purpose RD ownership boundary.
6. `README.md` — operator/repository overview.
7. `docs/DEPLOYMENT.md` — deployment, validation and rollback runbook.
8. `docs/RECOVERY_TRACE_REPLAY.md` — trace/replay tooling.

If code and these current documents disagree, stop and resolve the inconsistency; do not guess from an old comment, legacy test or historical commit.

## Control invariants

- Chemistry, intent, battery condition, program mode and actuator ownership are separate inputs.
- `Normal` is the full V1-compatible automatic chain: bounded recovery and final Mix may occur when deterministic evidence/strategy allows them.
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

## Deployment-only tasks

For a deployment request:

- Do not refactor code.
- Do not change `.env`, secrets, HA entity IDs, Telegram token or local runtime configuration unless explicitly requested.
- Preserve the existing service manager and service name discovered on the node.
- Back up the currently deployed working tree before replacing it.
- Check out the exact requested branch/SHA.
- Install/update `requirements.txt` in the existing Python environment.
- Run:

```bash
python -m compileall -q .
python -m unittest discover -s tests -p 'test_*.py'
```

- If tests fail, do not start the new service; restore/retain the previous deployment.
- After restart, verify service state and recent logs.
- Do not start a real charge or turn RD6018 output ON as a deployment smoke test.
- Do not deploy a new edge-lease/HANDS_OFF contract until the exact ESPHome node/package has been compiled, flashed and bench-validated together with the matching Python version.

## Test expectations

The branch is expected to pass the complete unittest matrix on Python 3.10, 3.11 and 3.12. Do not weaken or delete safety/control tests merely to make CI green.

For ownership/watchdog changes, fake Python lease tests are not sufficient by themselves. Keep an exact ESPHome contract test and a BENCH gate for the real node because Python and edge semantics must agree.

## Scope discipline

For narrow operational tasks, make only the requested operational changes. Do not redesign charging thresholds, recipes, Telegram UX or database schema unless the task explicitly asks for it.
