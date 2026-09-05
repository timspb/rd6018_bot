# RD6018 Telegram Bot — Pb Recovery Controller V2

Telegram controller for an RD6018 power supply through Home Assistant, with evidence-driven lead-acid charging/recovery logic and an explicit general-purpose PSU ownership mode.

This branch is the production V2 cutover. It is safety-critical code: the bot can command real voltage/current to a physical battery.

## Production entrypoint

```bash
python bot.py
```

`bot.py` is intentionally a small V2 entrypoint. The previous large Telegram/HA runtime is preserved as `bot_legacy.py` and is wrapped by the V2 bootstrap.

Production authority is layered:

```text
DiagnosticProductionChargeControllerV2
  -> V2 AUTO strategy + diagnostic HV veto + durable Mix time
  -> legacy safety/mechanics scaffold

ProductionManualSessionManager
  -> separate managed Manual authority

both
  -> V2RuntimeSafetyGuard
  -> SafeOutputCoordinator / HassClient
  -> edge safety lease
  -> Home Assistant / ESPHome
  -> RD6018

outer ownership boundary:
  RdControlModeManager -> PB_MANAGED / HANDS_OFF
```

For deployment and rollback use [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md). Agents should read [`AGENTS.md`](AGENTS.md) and the decision/strategy documents before changing control behavior.

## Core V2 model

Charging is not described by a battery profile alone. These concepts are separate:

- **chemistry**: AGM / EFB / Ca/Ca / Flooded / Custom;
- **intent**: Normal / Recovery / Conditioning / Diagnostic;
- **condition**: Unknown / Healthy / Sulfated suspected / Dry suspected / Rehydrated / Overwet suspected / Stratified suspected / Degraded;
- **program mode**: full AUTO / Auto Mix / Manual;
- **stage**: Prep / Main / Desulfation / Mix / SAFE_WAIT / Cooling / Done;
- **RD ownership**: PB_MANAGED / HANDS_OFF.

The durable behavior source of truth is [`docs/assistant/V2_DECISION_LOG.md`](docs/assistant/V2_DECISION_LOG.md). Current production strategy is summarized in [`docs/assistant/CHARGE_STRATEGY.md`](docs/assistant/CHARGE_STRATEGY.md).

## Production AUTO authority

For non-Custom profiles, V2 owns Main/Mix strategy decisions while the legacy controller remains a safety/mechanics scaffold.

- **Normal** is the full V1-compatible automatic chain. It may use bounded intermediate recovery and final Mix when deterministic evidence/strategy permits it.
- **Recovery** uses the same safety/evidence authority with an explicit recovery purpose/context.
- **Conditioning** is a service purpose inside the chemistry envelope; it does not bypass evidence or safety.
- **Diagnostic** is the explicit no-new-automatic-HV intent.
- ordinary legacy `Main -> HV` and `Mix -> finish` triggers are masked while V2 is authoritative;
- Custom remains legacy-authoritative because it is an explicit operator-defined contract.

Emergency strategy rollback:

```bash
V2_AUTHORITATIVE=0 python bot.py
```

## CV and CC are different physical observations

V2 does not interpret every finish through current.

### CV — voltage controlled

The independent battery response is current:

```text
I falls -> Imin -> confirmed current rise (delta-I)
```

The current Mix reversal evidence uses a relative term plus an instrument floor. A current rise by itself is not thermal-runaway evidence; voltage and temperature context still matter.

### CC — current controlled

The independent battery response is voltage:

```text
U rises -> Vmax -> confirmed voltage fall (delta-V)
```

In CC, regulated current is not used as the independent chemical finish signal.

## Mix timing and completion

Standard automatic Mix targets:

| Chemistry | Mix target | Maximum automatic active-Mix authority |
|---|---:|---:|
| AGM | 16.3 V | 10 h |
| EFB | 16.5 V | 24 h |
| Ca/Ca | 16.5 V | 20 h |

These times are **authority ceilings**, not target durations and not successful-completion evidence.

After valid mode-specific Delta evidence is confirmed, V2 starts a sticky two-hour finish hold. An accepted hold that began before the authority ceiling keeps its completion semantics unless independent safety wins.

Without an accepted finish hold at the chemistry ceiling:

```text
MIX_TIMEOUT
-> STOP_AND_DIAGNOSE
-> verified Output OFF
```

`MIX_TIMEOUT` never means successful SAFE_WAIT/Storage completion.

Production Mix time is durable active time, not reconstructed from Ah or raw wall-stage age. Proven Output OFF/Cooling freezes the budget; uncertain downtime after restart from a durable active state is conservatively charged.

## Initial AUTO start

The initial battery-voltage decision is made before first Output ON:

```text
Vbat < 12.0 V  -> PREP at ~0.01C
Vbat >= 12.0 V -> MAIN directly + PREP_SKIPPED audit
```

Auto Mix is a separate direct-entry program. It starts in Mix, never transiently enters PREP/Main/recovery, and rejects `Vbat < 12.0 V`.

## Recipe envelopes

Every automatic target is bounded after temperature compensation by chemistry, intent and stage.

Key production limits:

- Ca/Ca Main ~14.7 V; standard Mix 16.5 V.
- EFB Main ~14.8 V; generic AUTO/Recovery/Conditioning ceiling **16.5 V**.
- AGM Main 14.4 -> 14.6 -> 14.8 -> 15.0 V; standard Mix 16.3 V.
- global working-current ceiling: 12 A.
- global Manual/Custom outer working-voltage ceiling: 17.5 V.

The 17.5 V outer limit is **not** an EFB chemistry entitlement. There is no generic EFB expert flag that expands automatic/conditioning authority above 16.5 V. A future automatic EFB profile above 16.5 V would require an explicit model-specific, manufacturer-backed recipe and separate validation.

## Temperature compensation and safety

Base legacy compensation remains:

```text
V_compensated = V_base + k * (25 - temp_ext)
```

The chemistry recipe envelope is applied afterwards, so compensation cannot enlarge automatic authority beyond the accepted ceiling.

`temp_ext` is battery temperature. `temp_int` is RD6018/power-supply temperature and is not battery chemistry evidence. Vin is PSU-health telemetry, not Pb-FSM authority. `BAT_MODE` is observational, not software permission.

## Fail-closed managed Output enable

New V2 starts use `HassClient.safe_enable_output()` / `SafeOutputCoordinator` under the V2 runtime guard.

The managed sequence is:

```text
fresh telemetry
-> recipe/manual envelope validation
-> OVP
-> OCP
-> voltage
-> current
-> configured-value readback
-> second preflight
-> edge lease
-> Output ON
-> post-enable verification
```

Any unprovable managed enable fails closed. Commanded values, configured/readback values and measured physical values remain separate concepts.

There is intentionally no PB-managed idle action that simply turns RD6018 ON with arbitrary old setpoints.

## RD6018 general-purpose PSU mode — HANDS_OFF

RD6018 may also be used as a general-purpose PSU. The persistent operator mode:

```text
🔓 Режим РД — не лезь
```

transfers actuator ownership away from Pb automation.

In `HANDS_OFF`:

- an externally programmed Output ON is not an orphan Pb fault;
- Pb voltage/current envelopes, battery-temperature freshness and Pb protection geometry do not control the external PSU state;
- normal bot Output/V/I/OVP/OCP writes are blocked without issuing a compensating OFF;
- raw telemetry remains observable;
- the mode survives restart;
- intrinsic RD6018 protections are not disabled by the bot.

Releasing an **active managed** AUTO/Manual session is a destructive authority transfer and therefore uses a two-step, session-bound Telegram confirmation. It does not rewrite Output/V/I/OVP/OCP.

The edge contract deliberately distinguishes two operations:

```text
normal lease disarm
  -> requires direct confirmed Output OFF

live managed -> HANDS_OFF ownership release
  -> dedicated edge command
  -> requires healthy already-armed lease + fresh direct RD readback
  -> clears managed lease ownership without changing Output
  -> positive acknowledgement requires generation change + unarmed state
```

Renewals are suspended/serialized during the transfer so an in-flight heartbeat cannot re-arm the edge watchdog after release. If the live release command may have reached the edge but its acknowledgement is lost **after durable HANDS_OFF commit**, software does not silently roll back to PB control; HANDS_OFF remains the conservative authority and the operator is warned that the local watchdog may still turn Output OFF.

Returning to Pb control currently requires confirmed raw Output OFF and never silently revives an old AUTO session. Live Output-ON Pb adoption is separate D061-D063 work and is not yet implemented.

Detailed contract: [`docs/assistant/RD_HANDS_OFF_MODE.md`](docs/assistant/RD_HANDS_OFF_MODE.md).

## Communication-loss watchdog

Managed Pb operation uses an ESPHome-local dead-man lease:

- TTL 15 minutes;
- renewal cadence 5 minutes;
- positive ACK requires generation advance, fresh direct Modbus/readback and healthy trip/quarantine state;
- expiry/loss causes local repeated Output OFF attempts;
- late recovery cannot silently resume an expired managed charge.

The exact ESPHome package is part of the safety contract. Python unit tests do not substitute for compiling/flashing and bench-validating that exact package/node.

## Manual

Manual is first-class managed operator authority, not `Idle + Output ON`.

- operator chooses working V/I inside `0 < V <= 17.5 V`, `0 < I <= 12 A`;
- OVP/OCP are derived and cannot be weakened;
- Pb chemistry transitions do not run;
- timer/V/I/reach/delta rules are operator stop conditions, not chemistry evidence;
- active reconfiguration is verified OFF -> fresh safe-enable;
- persisted active Manual restores `INTERRUPTED`, never silently re-energizes, and requires explicit fresh reauthorization;
- optional saved battery identity is longitudinal metadata only and does not change Manual V/I.

## Diagnostics and calibration boundaries

Diagnostic inference is hypothesis-specific. A single score, one SG sample or one U/I sample cannot create a hard safety stop. Strong independent evidence is required to veto new automatic HV.

Specific gravity, dynamic-loop response, bank-fault calibration, external-temperature anomaly thresholds and adaptive Mix current actuation all retain explicit calibration/validation boundaries. In particular, the adaptive-current ratchet exists in software but has no production RD current/OCP actuator authority until Q005/Q014 physical characterization closes that gate.

## Telegram V2 workflow

Normal program flow:

```text
saved physical battery or chemistry
-> intent
-> capacity (for ad-hoc profile)
-> program preview
-> explicit Start
```

The operator UI distinguishes Normal full-auto, Diagnostic no-new-auto-HV, Manual, Auto Mix, explicit terminal OFF conditions and RD `HANDS_OFF` ownership.

UI rollback only:

```bash
V2_UI=0 python bot.py
```

## Battery history, traces and replay

V2 persists longitudinal battery/recovery evidence including physical battery identity, condition, refill history, Main/HV evidence, temperature behavior, relaxation windows and raw mode-specific traces. Replay/calibration tooling is documented in [`docs/RECOVERY_TRACE_REPLAY.md`](docs/RECOVERY_TRACE_REPLAY.md).

## Installation

Requirements:

- Python 3.10+;
- Home Assistant with RD6018 entities configured in `config.py`;
- Telegram bot token;
- external battery-temperature telemetry for managed Pb charging;
- matching ESPHome edge-lease package for enforced managed operation;
- DeepSeek API key only if optional AI analysis is used.

Basic development launch:

```bash
git clone https://github.com/timspb/rd6018_bot.git
cd rd6018_bot
git checkout refactor/pb-recovery-controller-v2
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m compileall -q .
python -m unittest discover -s tests -p 'test_*.py'
python bot.py
```

Do not treat this example as the deployment procedure for an existing node. Existing-node deployment is in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## Configuration

Runtime configuration is environment-based (`.env` / service environment). Important values include:

```env
TG_TOKEN=...
HA_URL=...
HA_TOKEN=...
HA_PREFER_LOCAL=1
HA_INSECURE_LOCAL=1
ALLOWED_CHAT_IDS=...

# Optional edge entity overrides
RD6018_EDGE_ENTITY_PREFIX=rd6018_rd_6018
RD6018_EDGE_HANDS_OFF_RELEASE_ENTITY=button.rd6018_rd_6018_safety_lease_release_to_hands_off

# Optional AI
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

Never commit real tokens. Do not replace an existing node's `.env` during deployment.

## Validation

Software preflight:

```bash
python -m compileall -q .
python -m unittest discover -s tests -p 'test_*.py'
```

CI runs the suite on Python 3.10, 3.11 and 3.12.

Passing CI proves only covered software contracts. It does **not** prove physical RD6018/Home Assistant/ESPHome/battery behavior. PR #2 remains Draft until the required BENCH/BAT gates in [`docs/assistant/V2_VALIDATION_PLAN.md`](docs/assistant/V2_VALIDATION_PLAN.md) are satisfied.

## Rollback

```bash
# Old Telegram UI only
V2_UI=0 python bot.py

# Legacy Main/Mix strategy authority
V2_AUTHORITATIVE=0 python bot.py

# Full rollback through production entrypoint
V2_UI=0 V2_AUTHORITATIVE=0 python bot.py

# Preserved old runtime directly
V2_AUTHORITATIVE=0 python bot_legacy.py
```

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) before changing a live node.

## Repository map

- `bot.py` — small production V2 entrypoint;
- `bot_legacy.py` — preserved previous Telegram/HA runtime;
- `v2_bootstrap.py` / V2 UI modules — composition and operator presentation;
- `diagnostic_controller.py` / `production_controller.py` — production AUTO composition;
- `charge_controller_v2.py` / `v2_authority.py` — V2 Main/Mix authority;
- `manual_mode.py` / `manual_runtime_v2.py` — Manual authority;
- `runtime_safety_v2.py` / `safe_output.py` / `hass_api.py` — managed actuator safety;
- `edge_safety_lease.py` / `esphome/rd6018_safety_lease.yaml` — local communication-loss lease contract;
- `rd_control_mode.py` / `rd_hands_off_release.py` — PB_MANAGED/HANDS_OFF ownership transfer;
- `battery_registry.py` / diagnostics and trace modules — longitudinal evidence;
- `docs/assistant/V2_DECISION_LOG.md` — durable behavior decisions;
- `docs/assistant/CHARGE_STRATEGY.md` — current strategy source of truth;
- `docs/assistant/RD_HANDS_OFF_MODE.md` — general-purpose PSU ownership contract;
- `docs/assistant/V2_VALIDATION_PLAN.md` — pre-merge software/bench/battery gates;
- `docs/DEPLOYMENT.md` — operational runbook;
- `AGENTS.md` — instructions for automation/coding agents.

## Safety notice

This software controls a real programmable power supply. High-voltage recovery modes can damage a battery, vehicle electronics or surrounding equipment if used incorrectly. Use an external battery temperature sensor for managed Pb charging, isolate batteries from vehicle electronics before recovery/HV work, and never treat green CI as physical validation.

## License

MIT. Use at your own risk.
