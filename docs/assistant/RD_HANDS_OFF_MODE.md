# RD6018 HANDS_OFF control mode

Status: **D060 implemented in software; HANDS_OFF safety-only external-Mix observer implemented; D061 managed Adopted Manual implemented in software and code-reviewed; D061 exact ESPHome compile/flash/bench validation remains pending; D062 managed adopted Mix is not implemented.**

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

## D060 active managed-session release

An already-running AUTO/Manual session can be released to HANDS_OFF without changing Output/V/I/OVP/OCP, but only through a two-step exact-session confirmation.

Ordinary edge `disarm()` remains OFF-only. Active Output-preserving release uses the dedicated edge command `Safety Lease Release To Hands Off`, accepted only from a healthy already-armed managed lease with fresh direct Modbus/Output readback and clear trip/quarantine state.

Python serializes lease renewal/release, requires positive generation/readback acknowledgement, and never silently rolls back to `PB_MANAGED` after durable HANDS_OFF if the edge ACK becomes ambiguous.

### Pre-commit safety OFF remains legal

The D060 transfer has a narrow `release_in_progress` barrier:

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

This preserves the OFF direction until the ownership boundary is actually committed. AUTO Mix durable authority is terminalized as `RELEASED_TO_RD_HANDS_OFF`; Manual runner/timers are retired software-only without calling the physical Manual stop path.

## Safety-only pickup of an external Mix while staying HANDS_OFF

The branch retains a deliberately narrow observer for an RD6018 Mix that was already running before the bot took ownership:

```text
external RD6018 Mix already ON
        ↓
HANDS_OFF
        ↓
🧲 Подхватить текущий Mix
        ↓
read raw V/I/OVP/OCP + HA Recorder history
        ↓
select exact saved physical battery
        ↓
fresh TOCTOU re-read
        ↓
choose:
  👁 observe only
  🎯 fresh Delta + 2h -> verified OFF
```

This observer **stays in HANDS_OFF**. It never writes V/I/OVP/OCP and never turns Output ON. `🎯 fresh Delta + 2h -> OFF` grants only bounded future verified-OFF authority. Successful completion remains HANDS_OFF; it does not enter SAFE_WAIT or Storage.

If final OFF cannot be confirmed, `OFF_PENDING` is durably persisted. Only that OFF containment may continue after restart; ordinary observer authority never resumes automatically.

### HA Recorder is context, not Delta authority

`ha_history.py` accepts prior session age only when Recorder contains an explicit uninterrupted:

```text
OFF -> ON -> ... -> current live ON
```

A window that merely begins ON is not authoritative age, and later `unknown`/`unavailable` invalidates it. Historical Imin/Vmax never seed V2 Delta/hold authority. Delta evidence begins only after explicit pickup and a new coherent source report; duplicate source reports do not accumulate confirmations. External V/I/OVP/OCP changes reset the observer Delta epoch.

## D061 — managed live adoption as Adopted Manual

D061 is separate from the HANDS_OFF observer. It is the only software path allowed to acquire `PB_MANAGED` while RD Output is already ON.

The implemented authority is deliberately **Adopted Manual**, not adopted Mix and not AUTO chemistry:

```text
HANDS_OFF + external Output ON
        ↓
read-only managed-envelope preflight
        ↓
select/confirm exact saved battery + chemistry + Adopted Manual
        ↓
durable ADOPTION_PENDING
        ↓
edge live-adoption read-only preflight
        ↓
fresh HA TOCTOU readback
        ↓
dedicated Safety Lease Adopt Live Output command
        ↓
positive edge ACK
        ↓
fresh HA TOCTOU readback
        ↓
PB_MANAGED + Adopted Manual
```

At the adoption point the bot does **not** write Output, voltage, current, OVP or OCP. The observed live V/I/OVP/OCP become component-wise maximum authority. Managed writes may only ratchet those values downward. Any out-of-band increase terminates the adoption toward verified OFF. If Output becomes OFF, Adopted Manual cannot re-energize it; a fresh managed program is required.

The preflight requires the ordinary managed safety envelope, including fresh coherent telemetry, normal protection state, legal positive V/I/OVP/OCP geometry, working-current/voltage ceilings, valid managed temperature-start range, and safe Boot Power/Take Out state when those registers are exposed.

### Exact edge contract required by D061

D061 does not infer compatibility from an accepted HTTP button call. Before the ownership command Python requires all of the following:

- dedicated `Safety Lease Adopt Live Output` entity;
- published `Safety Lease TTL` equal to the accepted 900 s contract;
- fresh authoritative raw register-16 `Protection Status Code == 0`;
- unarmed healthy HANDS_OFF edge state with effectively-zero remaining lease;
- fresh direct Modbus evidence.

The ESPHome command independently requires:

- exact `rd6018_safety_lease_ttl_ms == 900000`;
- fresh direct telemetry, register-18 Output-ON readback and register-16 protection readback;
- protection code exactly `0`;
- no trip/quarantine;
- no existing managed session.

Positive ACK requires generation change, healthy armed state, fresh direct Modbus evidence and a replenished near-full 900 s lease. Raw register-16 NORMAL is checked again after ACK and then remains mandatory on every managed poll, not merely on a five-minute renewal event.

### Pre-command vs post-command failure boundary

A code-review defect was fixed here deliberately. A race can fail after `prepare()` but before the button is actually invoked—for example generation/protection/TTL changing during the last read-only edge checks.

Those failures remain non-actuating:

```text
edge command not invoked
        -> stay HANDS_OFF
        -> external Output/settings untouched
```

Once command invocation begins, a transport/ACK error can no longer prove whether ESPHome changed ownership:

```text
edge command may have executed
        -> ownership ambiguous
        -> verified Output OFF containment
```

The edge helper exposes this uncertainty boundary explicitly; the coordinator no longer treats every exception from `adopt()` as evidence that the command was sent.

### Restart contract

Managed live authority never auto-resumes after process restart. Persisted `ADOPTION_PENDING`, `ACTIVE` or `OFF_PENDING` becomes startup OFF containment; verified Output OFF is required before fresh operator authorization.

## Current installed ESPHome is intentionally incompatible with D061

The currently deployed pre-D061 firmware is suitable for the present external HANDS_OFF observer but not for managed live adoption. The observed contract has the following blockers:

```text
local lease TTL              1800 s / 30 min
Safety Lease Adopt Live Output   absent
raw Protection Status Code       absent
published Safety Lease TTL       absent
current external OCP             0.0 A
```

`OCP=0` may be preserved as an explicit disabled-protection value while merely observing an external HANDS_OFF session, but it is not acceptable managed Pb protection authority. D061 never silently rewrites it during adoption.

The target safety package enters boot quarantine after ESP reboot and repeatedly forces Output OFF until fresh direct OFF proof. Therefore flashing/rebooting the target package while an occupied external Mix must continue is **not** a transparent upgrade. Flashing is a deliberate session-interrupting boundary.

## D062 — managed adopted Mix

Status: **accepted design / not implemented.**

D062 will be a separate `MIX_ADOPTED` authority, not Manual and not full AUTO. It must use the physically validated D061 edge ownership primitive and additionally:

- explicitly confirm battery and chemistry;
- account reliable/declared prior active Mix time against Ca20/EFB24/AGM10 authority;
- never invent a fresh chemistry budget when prior age is unknown;
- begin Delta evidence fresh after adoption;
- preserve current external settings as maximum authority rather than silently raising them to recipe defaults;
- finish accepted Delta + sticky hold in verified OFF, not SAFE_WAIT/Storage;
- end hard budget expiry as abnormal `MIX_TIMEOUT -> verified OFF + diagnose`.

No current code claims D062 managed Mix authority.

## D063 — unknown prior age

The safety-only HANDS_OFF observer implements the non-autonomous part of D063: Recorder may prove an `OFF -> ON` elapsed interval; otherwise age remains unknown, and no autonomous chemistry budget is created.

Full managed D062/D063 age authority is still absent. An unknown prior Mix age must never become a new Ca20/EFB24/AGM10 window merely because the bot was installed.

## Deployment over an already-running external session

For the current occupied session, use the HANDS_OFF observer path rather than D061 managed takeover:

```bash
python tools/prepare_hands_off_live_session.py --dry-run
python tools/prepare_hands_off_live_session.py
python bot.py
```

with the old service stopped during handover. The preflight tool reads current state/history, requires Output ON plus complete V/I/OVP/OCP readback, atomically prepares HANDS_OFF state, and never writes RD6018 Output or setpoints.

## Validation boundary

Python CI proves software contracts only. Before relying on D061 managed ownership transfer physically, the exact combined ESPHome safety-lease + telemetry + live-adoption package must be compiled, flashed and exercised on a dummy/load-safe setup. Required bench work includes TTL/raw-protection entity verification, Output/setpoint preservation, generation/ACK proof, pre-command race, ambiguous ACK, raw-protection loss, restart containment and local watchdog timing.

Because target firmware boot quarantine intentionally forces OFF after reboot, perform that bench/deployment only after the currently occupied external battery session can be interrupted.
