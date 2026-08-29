# RD6018 Telegram Bot — Pb Recovery Controller V2

Telegram controller for an RD6018 power supply through Home Assistant, with evidence-driven lead-acid charging/recovery logic.

This branch is the production V2 cutover. It is safety-critical code: the bot can command real voltage/current to a physical battery.

## Production entrypoint

```bash
python bot.py
```

`bot.py` is intentionally a small V2 entrypoint. The previous large Telegram/HA runtime is preserved as `bot_legacy.py` and is wrapped by the V2 bootstrap.

Production controller:

```text
ProductionChargeControllerV2
  -> ChargeControllerV2 evidence/transition authority
  -> legacy safety/mechanics scaffold
  -> chemistry + intent recipe envelope
  -> SafeOutputCoordinator / HassClient
  -> Home Assistant
  -> RD6018
```

For deployment and rollback use [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md). Agents should also read [`AGENTS.md`](AGENTS.md).

## Core V2 model

Charging is no longer described only by a battery profile. Four dimensions are separate:

- **chemistry**: AGM / EFB / Ca/Ca / Flooded / Custom;
- **intent**: Normal / Recovery / Conditioning / Diagnostic;
- **condition**: Unknown / Healthy / Sulfated suspected / Dry suspected / Rehydrated / Overwet suspected / Stratified suspected / Degraded;
- **stage**: Prep / Main / Desulfation / Mix / SAFE_WAIT / Cooling / Done.

Examples:

```text
AGM + NORMAL
AGM + REHYDRATED + RECOVERY
```

are intentionally different controller contexts.

The detailed strategy source of truth is [`docs/assistant/CHARGE_STRATEGY.md`](docs/assistant/CHARGE_STRATEGY.md).

## Production authority

For non-Custom profiles, V2 is actuator-authoritative for Main/Mix transition decisions.

- Normal and Diagnostic never automatically escalate to Recovery HV/Mix.
- Recovery and Conditioning may enter HV only after V2 evidence and recipe authorization.
- legacy `ChargeController.tick()` remains as the proven scaffold for telemetry validation, temperature safety, hard timeout, SAFE_WAIT/Cooling, restore and persistence;
- ordinary legacy `Main -> HV` and `Mix -> finish` triggers are masked while V2 authority is enabled;
- Custom remains legacy-authoritative because it is an explicit operator-defined contract.

Emergency rollback:

```bash
V2_AUTHORITATIVE=0 python bot.py
```

## CV and CC are different physical observations

V2 never interprets every finish through current.

### CV — voltage is controlled

The independent battery response is current:

```text
I falls -> Imin -> confirmed current rise (delta-I)
```

Current working Mix reversal threshold:

```text
max(0.03 A instrument floor, 0.30 * Imin)
```

A current rise by itself is not treated as thermal runaway. Voltage and temperature behavior provide the context.

### CC — current is controlled

The independent battery response is voltage:

```text
U rises -> Vmax -> confirmed voltage fall (delta-V)
```

Current CC observation threshold is `0.03 V` with confirmation/hysteresis.

In CC, regulated current is not used as the independent chemical finish signal.

## Mix timing

Recovery Mix base/fallback windows:

| Chemistry | Mix base | Evidence-search fallback window |
|---|---:|---:|
| AGM | 16.3 V | 10 h |
| EFB | 16.5 V | 20 h |
| Ca/Ca | 16.5 V | 20 h |

After a valid CV delta-I or CC delta-V is confirmed, V2 starts a **sticky 2-hour finish hold**.

The profile window is a fallback deadline while searching for evidence. It does not cancel an already-active finish hold. Thermal, telemetry, communication and hardware safety always outrank the hold.

## Main / HV behavior

V2 replaces the old universal `0.2 A / 0.3 A` interpretation with capacity-normalized evidence.

- tail current is interpreted relative to battery Ah;
- a new minimum resets tail age;
- sufficiently old/stable tail may allow progression;
- persistent plateau above roughly `1%C` is not treated as an automatic reason to increase voltage;
- abnormal thermal or voltage behavior prevents automatic HV escalation.

AGM Main still uses stepped base targets:

```text
14.4 -> 14.6 -> 14.8 -> 15.0 V
```

but V2 evidence owns advancement toward recovery HV.

## Recipe envelopes

Every production target is bounded **after temperature compensation** by chemistry + intent.

| Chemistry | Normal / Diagnostic | Recovery | Conditioning without expert authorization |
|---|---:|---:|---:|
| AGM | 15.0 V | 16.3 V | 16.3 V |
| EFB | 14.8 V | 16.5 V | 16.5 V |
| Ca/Ca | 14.7 V | 16.5 V | 16.5 V |
| Flooded | 14.8 V | 16.5 V | 16.5 V |

The policy model contains an explicit EFB expert envelope up to 17.5 V, but the normal Telegram V2 workflow does **not** authorize it automatically.

Pre-V2 session files have no intent. They are migrated conservatively as `NORMAL`, and restored setpoints are re-bounded by the resulting recipe envelope.

## Temperature compensation and safety

Base legacy compensation remains:

```text
V_compensated = V_base + k * (25 - temp_ext)
```

- Ca/Ca and EFB: `0.018 V/°C`;
- AGM: `0.016 V/°C`;
- Custom: `0.018 V/°C`;
- legacy compensation delta is clamped to ±0.60 V;
- V2 recipe envelope is applied afterwards.

`temp_ext` is battery temperature. `temp_int` is controller/power-supply temperature and must not be interpreted as battery chemistry evidence.

Existing hard safety remains independent of the recipe, including global current ceiling, battery thermal protection, OVP/OCP, watchdogs and HA communication-loss handling.

## Fail-closed RD6018 output enable

New V2 starts use `HassClient.safe_enable_output()` / `SafeOutputCoordinator`.

The required sequence is:

```text
fresh telemetry
-> recipe + absolute envelope validation
-> OVP
-> OCP
-> voltage
-> current
-> readback verification
-> second preflight
-> output ON
-> post-enable verification
```

Any failure forces/leaves output OFF. Telegram reports a successful start only after output enable is confirmed.

There is intentionally no V2 idle action that simply turns RD6018 ON with arbitrary old setpoints.

## Telegram V2 workflow

Normal program flow:

```text
chemistry or saved physical battery
-> intent
-> capacity (for ad-hoc profile)
-> program preview
-> explicit Start
```

Main V2 surfaces include:

- `🔋 АКБ` — physical battery registry/history;
- `🧭 V2` — current evidence/controller card;
- lifecycle fields: condition, refill/water history, cycles since refill, measured capacity, CCA and Ri;
- CV status emphasizes Imin/delta-I/current trend;
- CC status emphasizes Vmax/delta-V/voltage trend;
- Normal preview explicitly states that automatic recovery HV is disabled.

UI rollback only:

```bash
V2_UI=0 python bot.py
```

## Battery history, traces and replay

V2 persists longitudinal battery/recovery evidence:

- physical battery identity and chemistry;
- condition and rehydration/refill state;
- Main/HV evidence and time-to-target;
- temperature behavior;
- relaxation windows;
- measured capacity, CCA and internal resistance;
- raw mode-specific CV/CC traces;
- replay/calibration reports with frozen thresholds.

Replay tooling is documented in [`docs/RECOVERY_TRACE_REPLAY.md`](docs/RECOVERY_TRACE_REPLAY.md).

## Installation

Requirements:

- Python 3.10+;
- Home Assistant with the RD6018 entities configured in `config.py`;
- Telegram bot token;
- external battery temperature telemetry for safe V2 start;
- DeepSeek API key only if AI analysis is used.

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

# Optional AI
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

Never commit real tokens. Do not replace an existing node's `.env` during deployment.

HA entity names are defined by `ENTITY_MAP` in `config.py`.

## Validation

Local/CI preflight:

```bash
python -m compileall -q .
python -m unittest discover -s tests -p 'test_*.py'
```

CI runs the suite on Python 3.10, 3.11 and 3.12.

Passing CI proves software regressions covered by the test suite; it does **not** prove physical RD6018/Home Assistant/battery behavior. Physical charging validation must be a separate controlled step.

## Rollback

```bash
# Old Telegram UI only
V2_UI=0 python bot.py

# Legacy Main/Mix authority only
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
- `v2_bootstrap.py` / `v2_bot_ui.py` / `v2_ui.py` — V2 bootstrap and presentation;
- `production_controller.py` — final recipe-bounded production controller;
- `charge_controller_v2.py` — V2 authority integration;
- `v2_authority.py` — evidence-driven Main/Mix decisions;
- `signal_analyzer.py` — CV/CC signal analysis;
- `recipe_engine.py` — chemistry/intent envelopes;
- `safe_output.py` / `hass_api.py` — fail-closed actuator boundary;
- `battery_registry.py` — physical battery and longitudinal recovery history;
- `recovery_trace_store.py` / replay/report modules — live evidence and calibration;
- `charge_logic.py` — legacy FSM/safety/mechanics scaffold and Custom behavior;
- `docs/assistant/CHARGE_STRATEGY.md` — charging strategy source of truth;
- `docs/assistant/PB_RECOVERY_V2.md` — architecture/invariants;
- `docs/DEPLOYMENT.md` — operational runbook;
- `AGENTS.md` — instructions for automation/coding agents.

## Documentation order for maintainers and agents

1. `AGENTS.md`
2. `README.md`
3. `docs/DEPLOYMENT.md` for operations
4. `docs/assistant/CHARGE_STRATEGY.md` for charging semantics
5. `docs/assistant/PB_RECOVERY_V2.md` for architecture
6. code/tests

Do not infer current production behavior from old commit history or legacy comments when these sources disagree.

## Safety notice

This software controls a real programmable power supply. High-voltage recovery modes can damage a battery, vehicle electronics or surrounding equipment if used incorrectly. Use an external battery temperature sensor, isolate the battery from vehicle electronics before recovery/HV work, and do not perform unattended hardware validation merely because CI is green.

## License

MIT. Use at your own risk.
