# AGENTS.md

This repository controls a physical RD6018 power supply and lead-acid batteries. Treat actuator changes as safety-critical.

## Production entrypoint

- Production: `python bot.py`
- `bot.py` is intentionally a small V2 entrypoint.
- The preserved previous Telegram/HA runtime is `bot_legacy.py`.
- Production controller: `ProductionChargeControllerV2` from `production_controller.py`.

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

1. `README.md` — current architecture and operator overview.
2. `docs/DEPLOYMENT.md` — deployment, validation and rollback runbook.
3. `docs/assistant/CHARGE_STRATEGY.md` — current charging/control semantics.
4. `docs/assistant/PB_RECOVERY_V2.md` — V2 architecture and invariants.
5. `docs/RECOVERY_TRACE_REPLAY.md` — trace/replay tooling.

If code and old comments/documents disagree, stop and resolve the inconsistency; do not guess.

## Control invariants

- Chemistry, intent and battery condition are separate inputs.
- Normal/Diagnostic must never automatically gain Recovery high-voltage authority.
- Recovery/Conditioning high voltage requires V2 evidence and recipe authorization.
- CV finish evidence is current-based: `Imin -> confirmed delta-I`.
- CC finish evidence is voltage-based: `Vmax -> confirmed delta-V`.
- Confirmed Mix delta starts a sticky 2-hour finish hold; profile fallback windows are AGM 10 h, Ca/Ca 20 h, EFB 20 h.
- Independent thermal, telemetry, hardware and communication safety outrank all finish/transition logic.
- Output enable must remain transactional and fail-closed through `HassClient.safe_enable_output()` / `SafeOutputCoordinator`.
- Never reintroduce a generic UI action that turns RD6018 ON with arbitrary pre-existing setpoints.

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

## Test expectations

The branch is expected to pass the complete unittest matrix on Python 3.10, 3.11 and 3.12. Do not weaken or delete safety/control tests merely to make CI green.

## Scope discipline

For narrow operational tasks, make only the requested operational changes. Do not redesign charging thresholds, recipes, Telegram UX or database schema unless the task explicitly asks for it.
