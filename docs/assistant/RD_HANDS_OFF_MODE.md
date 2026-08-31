# RD6018 HANDS_OFF control mode

Status: **D060 implemented in software; D061 safety-only live-session pickup implemented; full managed D062 live Mix adoption remains pending. Exact ESPHome compile/flash/bench validation is still required for managed edge ownership transfer.**

## Why this mode exists

RD6018 is a general-purpose programmable power supply first. Pb charging is only one use of it. The durable ownership modes are:

```text
PB_MANAGED
HANDS_OFF
```

`PB_MANAGED` gives V2 charging/safety code actuator authority. `HANDS_OFF` explicitly gives physical RD6018 ownership back to the operator.

## D060 — general-purpose PSU / HANDS_OFF

In `HANDS_OFF`:

- `Output ON` is not an orphan Pb fault;
- Pb voltage/current envelopes and Pb OVP/OCP geometry do not own the external PSU state;
- stale/missing `temp_ext` does not cause Pb shutdown;
- normal bot writes for Output ON/OFF, voltage, current, OVP and OCP are rejected without compensating actuation;
- raw HA/RD telemetry remains readable;
- intrinsic RD6018 protections remain whatever the RD6018 itself is configured to enforce;
- mode persistence survives process restart;
- stale pre-HANDS_OFF AUTO restore authority is cleared rather than silently revived.

The separate Telegram action `⏹ Output OFF` is the only ordinary actuator exposed by D060 while HANDS_OFF is active. It uses the captured raw Output command and succeeds only after raw switch readback proves OFF. It does not return Pb authority.

`🔒 Вернуть контроль заряда` requires no stale managed AUTO/Manual authority and raw Output positively OFF. It does not energize the RD6018.

## Active managed-session release

An already-running AUTO/Manual session can be released to HANDS_OFF without changing Output/V/I/OVP/OCP, but only through a two-step exact-session confirmation.

Ordinary edge `disarm()` remains OFF-only. Active Output-preserving release uses the dedicated edge command `Safety Lease Release To Hands Off`, which is accepted only from a healthy already-armed managed lease with fresh direct Modbus/Output readback and clear trip/quarantine state.

Python serializes lease renewal/release, requires positive generation/readback acknowledgement, and never silently rolls back to `PB_MANAGED` after durable HANDS_OFF if the edge ACK becomes ambiguous.

### Pre-commit safety OFF remains legal

The transfer has a narrow `release_in_progress` barrier:

```text
PB_MANAGED remains in memory
new Output ON / setpoint writes blocked
managed get_all_live heartbeat bypassed
verified Output OFF still allowed
        ↓
edge release API preflight
        ↓
durable HANDS_OFF write
        ↓
in-memory HANDS_OFF
        ↓
edge ownership release + software retirement
```

This is deliberate. A previous implementation temporarily set in-memory HANDS_OFF before the durable ownership commit, which could also block a concurrent safety-driven `turn_off()`. The current implementation keeps the OFF direction available until the ownership boundary is actually committed.

AUTO Mix durable authority is terminalized as `RELEASED_TO_RD_HANDS_OFF`; Manual runner/timers are retired software-only without calling the physical Manual stop path.

## D061 — live external-session pickup while HANDS_OFF

The current branch now implements a **non-autonomous/safety-only** pickup for an RD6018 Mix that was already running before the bot took ownership.

Operator flow:

```text
external RD6018 Mix already ON
        ↓
start bot in durable HANDS_OFF
        ↓
🧲 Подхватить текущий Mix
        ↓
read current raw V/I/OVP/OCP + HA Recorder history
        ↓
select exact saved physical battery
        ↓
fresh TOCTOU re-read of current setpoints
        ↓
choose:
  👁 observe only
  🎯 fresh Delta + 2h -> verified OFF
```

The observer **stays in HANDS_OFF**. It never writes V/I/OVP/OCP and never turns Output ON. Therefore it does not claim full Pb actuator ownership and does not require a live edge-lease adoption transaction for the already-running output.

`🎯 fresh Delta + 2h -> OFF` grants only one bounded future actuator authority: after a new post-confirmation V2 Delta and the normal 2-hour finish hold, issue verified Output OFF. Successful completion remains HANDS_OFF; it does not enter SAFE_WAIT or Storage.

If final OFF cannot be confirmed, `OFF_PENDING` is durably persisted. That containment is the only observer authority allowed to survive process restart; startup retries toward verified OFF. A normal active observer never resumes after restart and requires fresh operator authorization.

## Home Assistant Recorder import

`ha_history.py` reads the documented Home Assistant `/api/history/period` endpoint. The live-session preview first retrieves Output history over the configured lookback and accepts prior session age only when Recorder contains an explicit uninterrupted:

```text
OFF -> ON -> ... -> current live ON
```

A query window that merely starts with `ON` is not enough to prove start time. A later `unknown`/`unavailable` also invalidates authoritative age.

For the detected running interval the preview summarizes recorded current, output voltage, battery voltage, external temperature and configured V/I where available. This is intentionally useful for the present experiment: the operator can immediately see historical extrema such as an earlier current minimum/maximum without losing them when the new bot is installed.

### History is context, not Delta authority

Recorder history does **not** seed V2 `Imin`, `Vmax`, Delta confirmations or the 2-hour hold. Those begin only after the operator confirms pickup and a new coherent HA source report arrives after that confirmation.

This prevents an old Recorder point, a duplicated poll or a partial historical record from becoming an actuator decision. Duplicate source reports do not accumulate confirmations. If the operator changes V/I/OVP/OCP externally, the observer keeps HANDS_OFF ownership but discards the old Delta epoch and waits for a new source report.

## D062 — full managed adopted Mix

Status: **accepted design / not yet implemented.**

A future full managed live adoption is a separate authority from Manual and full AUTO. It must:

- explicitly confirm battery and chemistry;
- preserve current external setpoints as maximum granted authority rather than silently increasing them to recipe defaults;
- account reliable prior active Mix time against Ca20/EFB24/AGM10 chemistry authority;
- start Delta evidence fresh at adoption;
- end normal adopted-Mix completion in verified OFF, not SAFE_WAIT/Storage;
- require a positive local edge ownership-adoption handshake before `PB_MANAGED` can own an already-ON output.

That edge adoption path is intentionally not faked in software while the current physical ESPHome package has not been bench-validated for it.

## D063 — unknown prior age never becomes a new chemistry budget

The current implementation now has the first half of D063:

- Recorder can provide a reliable prior `OFF -> ON` elapsed time when the evidence exists;
- otherwise age remains explicitly unknown;
- the HANDS_OFF observer remains available regardless, because it does not grant autonomous HV continuation authority;
- the UI displays the normal chemistry Mix maximum and warns when Recorder age is already at/above it.

What is still **not** implemented is converting that age into a new full managed adopted-Mix budget. In particular, no code grants a fresh Ca20/EFB24/AGM10 window merely because the bot was just installed.

## Deployment over an already-running external session

Do not start a fresh branch build in default `PB_MANAGED` over an unknown already-ON RD6018 and hope it infers ownership. The production orphan guard is supposed to reject that.

Use:

```bash
python tools/prepare_hands_off_live_session.py --dry-run
python tools/prepare_hands_off_live_session.py
python bot.py
```

with the old service stopped during the handover. The preflight tool:

- reads current HA/RD state;
- requires Output positively ON plus complete V/I/OVP/OCP readback;
- reads Recorder history for context;
- atomically prepares `rd_control_mode_v2.json` as HANDS_OFF;
- never writes Output or any RD6018 setpoint.

After startup the Telegram dashboard exposes `🧲 Подхватить текущий Mix` while Output is ON.

## Validation boundary

Python CI proves only software contracts. For the present externally-running battery, the HANDS_OFF observer path does not require changing/flashing ESPHome because it does not acquire managed lease authority or rewrite output state. The D060 managed-session release handshake and any future D062 full managed live adoption still require exact ESPHome compile/flash and controlled bench validation before physical reliance.
