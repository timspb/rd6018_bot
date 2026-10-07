# RD6018 Telegram Bot — modular production controller

This repository contains the current modular production controller for an RD6018 power supply used for evidence-driven lead-acid charging/recovery and explicit general-purpose PSU ownership.

The software is safety-critical: it can command real voltage/current to physical hardware. Production behavior is fail-closed and separates operator UI, charge-domain decisions, telemetry evidence, safety/execution policy, ownership/session state, persistence, and physical execution.

## Production entrypoint

```bash
python bot.py
```

`bot.py` is a small composition/lifecycle entrypoint. It does not contain a legacy runtime fallback and must not grow one.

The current ownership path is:

```text
Telegram/operator UI
  -> application intent / production START route
  -> charge strategy + diagnostics/evidence
  -> safety + execution policy
  -> ownership/session + lease
  -> physical bridge
  -> HA-ESP or ESP-direct connector
  -> RD6018
  -> independent readback/evidence
```

HA-ESP and ESP-direct are independent connectors to the same RD6018. They are not an automatic fallback chain.

## Current architecture authority

Read these before changing production behavior:

- `docs/V3_PROJECT_RUNBOOK.md` — current project state and chronological operational evidence.
- `docs/V3_MODULAR_ARCHITECTURE.md` — mandatory module and ownership boundaries.
- `docs/V3_UI_MODULAR_ARCHITECTURE.md` — UI/application/transport boundary.
- `docs/RD6018_COMPOSITION_ROOT_MODEL.md` — composition-root contract.
- `docs/RD6018_FAILSAFE.md` — physical/edge fail-safe rules.
- `docs/DEPLOYMENT.md` — deployment and rollback.
- `docs/README.md` — documentation authority index.

Older phase/V2/V3 migration documents are historical evidence unless the documentation index explicitly marks them current.

## Production model

Charging separates chemistry, operator intent, battery condition, program mode, charge stage, and RD ownership. Current automatic decisions belong to modular charge strategy/runtime owners rather than a historical FSM.

Safety-relevant invariants include:

- fresh/valid telemetry before managed energization;
- chemistry/recipe envelopes for automatic voltage/current authority;
- explicit OVP/OCP and configured-value readback;
- ownership/session reconciliation before START;
- edge lease/dead-man behavior during managed operation;
- fail-closed handling of stale or contradictory evidence;
- verified Output OFF/readback for terminal/containment transitions;
- no implicit automatic fallback between physical connectors.

Persisted/session keys, Telegram callback-data tokens and external telemetry entity IDs are protocol/state boundaries. Historical-looking tokens that remain there must not be renamed by textual cleanup alone.

## Physical layer

The current physical model is:

```text
PhysicalBridge contract
       |
   +---+---+
   |       |
HA-ESP   ESP-direct
   |       |
   +---RD6018
```

Physical execution is separate from repository cleanup. Green CI proves software contracts only; it does not authorize hardware mutation.

The project has recorded controlled physical evidence in the V3 runbook and dated evidence documents. Any new physical run must follow the current bench protocol and explicit operator authorization.

## Development

Requirements are defined by the repository. A basic development checkout is:

```bash
git clone https://github.com/timspb/rd6018_bot.git
cd rd6018_bot
python -m venv .venv
# activate the environment for your platform
python -m pip install -r requirements.txt
python -m compileall -q .
python -m unittest discover -s tests -p 'test_*.py'
python bot.py
```

Do not treat this as an existing-node deployment procedure. Use `docs/DEPLOYMENT.md` for deployment/rollback.

## Configuration

Secrets are environment references and must never be committed. Physical, charge, safety and runtime configuration belong to their typed/current owners rather than duplicated literals in consumers.

Typical environment values include Telegram and Home Assistant credentials. Preserve an existing node's environment during deployment; do not replace credentials as part of code cleanup.

## Repository rules

- Do not recreate removed legacy/compatibility/shadow modules as forwarding shims.
- Do not put direct hardware control in the Telegram/UI layer.
- Do not bypass SafetyEngine/execution policy/ownership/lease/readback boundaries.
- Do not introduce parallel unsynchronized charge FSMs.
- Do not hardcode safety/charge policy values in unrelated consumers.
- Do not infer physical authorization from passing unit tests or CI.
- Keep current authority docs synchronized with merged production code.

## Validation

Repository changes require, as applicable:

```bash
python -m compileall -q .
git diff --check
python -m unittest discover -s tests -p 'test_*.py'
```

GitHub exact-head CI runs the supported Python matrix. Architectural changes are merged only after the exact PR head passes.

## Safety notice

This software controls a real programmable power supply. High-voltage recovery modes can damage batteries, vehicle electronics, wiring, or surrounding equipment. Follow the current fail-safe and bench-validation procedures, use independent readback, and keep physical execution separate from software-only repository work.

## License

MIT. Use at your own risk.
