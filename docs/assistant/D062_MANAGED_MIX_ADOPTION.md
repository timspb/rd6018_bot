# D062 / D063 — managed adoption of an already-running external Mix

Status: **software contract implemented; original D061 edge primitive physically validated; refreshed source-heartbeat firmware/bot pairing and full D062 physical takeover remain pending. Do not claim physical managed-Mix takeover ready yet.**

D062 is intentionally separate from both D061 Adopted Manual and the HANDS_OFF external-Mix observer:

- D061 Adopted Manual transfers low-level ownership but grants no chemistry/Mix completion authority.
- The HANDS_OFF observer keeps low-level ownership external and may gain only bounded safety/verified-OFF authority.
- D062 `MIX_ADOPTED` transfers the already-running high-voltage Mix into `PB_MANAGED` and grants only the bounded chemistry authority required to observe that existing Mix through Delta/timeout to verified OFF.

It is not a shortcut into full AUTO and it never creates PREP/Main/Recovery/SAFE_WAIT/Storage transitions.

## Preconditions

A D062 takeover requires all of the following before the edge command may execute:

1. Durable outer mode is `HANDS_OFF` and Output is positively confirmed ON.
2. No AUTO, Manual, D061 Adopted Manual or HANDS_OFF Mix observer currently owns authority.
3. A saved physical Pb battery is explicitly selected and its chemistry/capacity are known.
4. The observed set voltage is already in the chemistry's high-voltage Mix envelope and does not exceed its recovery ceiling.
5. Current is inside the chemistry/capacity HV current envelope and the generic absolute current limit.
6. D061 managed live-adoption preflight accepts fresh coherent telemetry, temperature, raw protection and positive protected V/I/OVP/OCP geometry.
7. Prior active Mix age is established under D063.
8. The resulting prior age has not already exhausted Ca/Ca 20 h, EFB 24 h or AGM 10 h.
9. The exact D061 edge live-adoption primitive is present and compatible.

The current occupied external session with `OCP = 0.0 A` remains valid for HANDS_OFF observation but is **not eligible for D062 managed takeover**, because D061 managed protection authority requires positive protective geometry. D062 must not repair that by writing OCP during acquisition.

## No-reprogram takeover

The accepted transaction is:

```text
HANDS_OFF + external Output ON
        ↓
read-only live fingerprint
        ↓
explicit physical battery / chemistry selection
        ↓
D063 prior-age proof or explicit declaration
        ↓
managed-Mix preview + exact confirmation
        ↓
fresh HA preflight and age re-resolution
        ↓
durable ADOPTION_PENDING
        ↓
D061 edge prepare
        ↓
fresh TOCTOU live fingerprint
        ↓
D061 edge Adopt Live Output invocation
        ↓
positive edge ACK
        ↓
fresh post-ACK TOCTOU fingerprint
        ↓
PB_MANAGED / MIX_ADOPTED
```

At no point in a successful takeover does D062 write Output, Vset, Iset, OVP or OCP. The live fingerprint becomes component-wise maximum authority. Later managed or external reductions may only ratchet the authority downward. An increase above the accepted authority is an out-of-band contradiction and terminates toward verified Output OFF.

D062 never calls Output ON. If Output becomes OFF, the adopted authority is retired and a fresh managed program is required for any future energization.

## D063 prior-age authority

The age budget is deliberately conservative because D062 begins observing after the external Mix has already been running.

HA Recorder may establish prior active age only when it proves an uninterrupted sequence with an explicit current-session edge:

```text
OFF -> ON -> ... -> current ON
```

If the Recorder window begins already ON, contains unknown/unavailable output state after the candidate edge, or otherwise cannot prove continuity, Recorder does not establish age.

When Recorder cannot prove age, D062 requires an explicit operator declaration. The declaration is elapsed **active Mix time**, conservatively rounded upward by the operator. No declaration means no managed takeover; remain HANDS_OFF/observer, use Manual where appropriate, or turn Output OFF.

The age accepted at preview is an immutable conservative floor:

```text
preview floor aged to now
fresh reliable Recorder age aged to now
explicit operator declaration aged to now
                ↓
             maximum
```

Therefore:

- a later Recorder query may increase prior age but can never reduce it;
- a Recorder outage between preview and Execute cannot erase or shrink the accepted floor;
- when both reliable Recorder and an operator declaration exist, the larger value wins;
- late observation never grants a fresh full Ca20/EFB24/AGM10 budget.

Recorder current/voltage/temperature summaries are context only. Historical Imin/Vmax or apparent historical reversal **never** seed actuator Delta authority.

## Active-time budget

After takeover:

```text
used Mix authority = accepted prior active age + post-adoption active time
```

The chemistry maxima remain:

```text
Ca/Ca  20 h
EFB    24 h
AGM    10 h
```

If no accepted fresh finish hold has started when the active-time budget reaches the boundary:

```text
MIX_TIMEOUT
  -> verified Output OFF
  -> diagnose/operator judgement
```

This is abnormal termination, never successful completion.

If a fresh Delta finish event was accepted **before** the budget boundary, its sticky 2 h hold owns completion and may finish after the boundary. Hard electrical/thermal/telemetry/edge safety still outranks the hold.

## Fresh Delta only

D062 resets its signal analyzer at successful adoption. The source timestamp barrier is set to the adoption epoch, so pre-adoption HA samples and Recorder history cannot count toward Delta.

Only distinct newer source reports may advance the analyzer. The finish rule remains mode-specific:

- CV: fresh Imin followed by accepted Delta-I reversal;
- CC: fresh Vmax followed by accepted Delta-V fall.

An external or managed decrease of V/I/protection authority starts a fresh Delta epoch because the operating point changed. Duplicate source reports do not accumulate confirmations.

Successful Delta + sticky 2 h completion performs verified Output OFF. D062 never enters SAFE_WAIT or Storage because it did not own the pre-existing charge history needed to claim ordinary AUTO completion.

## Transaction-local edge uncertainty

D062 must not use a stale `edge.command_may_have_executed` value from an earlier operation as evidence about the current transaction.

The current transaction boundary is:

```text
preflight / age / edge.prepare / second TOCTOU
    failure -> read-only reject; HANDS_OFF external program remains untouched

edge.adopt() invocation
    command definitely not sent -> read-only reject
    command may have executed / ACK ambiguous -> verified-OFF containment

post-ACK TOCTOU
    contradiction after ownership may have moved -> verified-OFF containment
```

This distinction prevents a historical ambiguity flag from turning off an unrelated external Mix merely because a later read-only D062 preflight failed.

## Restart containment

D062 persists the adoption lifecycle. A process restart with prior state `ADOPTION_PENDING`, `ACTIVE` or `OFF_PENDING` never resumes HV authority. The restored state becomes OFF containment and startup recovery may only complete verified Output OFF, after which a fresh operator decision/program is required.

A normal external Output OFF also retires `MIX_ADOPTED`; it is not re-energized.

## Telegram/HMI contract

From HANDS_OFF + Output ON the operator may select **Забрать Mix под управление** only when the current set voltage can plausibly be a supported chemistry high-voltage Mix. The workflow remains read-only through battery selection, prior-age resolution and preview. A separate final confirmation precedes edge execution.

The pre-selection HMI filter is deliberately only a coarse impossibility gate because chemistry is not yet known. Exact eligibility remains chemistry-specific after the physical battery is selected: set voltage must be above that chemistry's normal ceiling and at/below its recovery ceiling, with its HV current envelope and all D061 protection/freshness gates satisfied.

While active, the main HMI must show `MIX_ADOPTED`, the selected battery, current authority, total used chemistry budget and either fresh Delta progress or sticky-hold progress. The primary destructive action is stop-only and performs verified Output OFF; legacy power toggle or PB restore must not be exposed as a substitute.

D062 callbacks belong to the same L3/L4 terminal-panel workspace discipline as the existing HANDS_OFF observer and D061 workflows. Execute/cancel/stop-execute close the workspace and republish the authoritative L2 panel.

## 2026-09-03 HMI eligibility finding

During a real D061 preparation run, HANDS_OFF was active with Output ON at:

```text
Vset = 13.60 V
Iset = 0.20 A
OVP  = 13.80 V
OCP  = 0.40 A
```

The old composed Telegram panel incorrectly exposed both:

```text
🧲 Подхватить текущий Mix
🎯 Забрать Mix под управление
```

At `13.60 V`, the external program is not a high-voltage Mix for any currently supported D062 chemistry. The existing deeper D062 `_chemistry_preflight()` would eventually reject it after battery selection, so the actuator authority itself was not widened, but the top-level HMI was misleading and stale Telegram callback messages could still reopen the inapplicable flow.

Code-bearing fix `28dd548bfddbb4a4913a1fd64be26c7bd3ededfa` adds a shared generic Mix-entry gate:

- before chemistry selection, Mix actions are shown only when set voltage is above the lowest possible supported high-voltage boundary derived from the same D062 chemistry policies/tolerance;
- if the current setpoint is definitely non-Mix, both HANDS_OFF Mix actions are removed while ordinary `🔒 Забрать под Pb-контроль` D061 and Output OFF remain available;
- old Telegram `rd_live_mix` / `rd_managed_mix` callbacks are revalidated against the current live setpoint so an obsolete message cannot bypass the UI filter;
- after battery selection, the existing chemistry-specific D062 envelope remains authoritative and may still reject a voltage/current that passed the coarse pre-selection filter.

The same commit also corrects stable HA source-heartbeat publication needed by D061/D062 freshness; it does not relax the 20 s freshness requirement.

Exact-head validation for this code-bearing fix:

```text
CI #1091                 SUCCESS
ESPHome firmware #29     SUCCESS
```

No D062 takeover was performed during the 13.60 V run. The connected battery was used only for the D061 preflight, which failed read-only before any edge adoption command because the old `battery_voltage` HA heartbeat was stale. Therefore **D062/D063 physical status remains PENDING**.

## Required physical bench gate

Software CI is not physical takeover validation. Before relying on D062 on a real battery, first pass the complete D061 bot/runtime gate in `D061_MANAGED_LIVE_ADOPTION.md`, then additionally prove D062 on an appropriate safe setup:

1. Exact combined corrected ESPHome node package compiles and is physically flashed/verified.
2. Published TTL is exactly 900 s and raw register-16 protection semantics are correct.
3. Critical HA source heartbeats remain fresh while stable, including the read-only register-18 Output state source.
4. Start an external high-voltage Mix with legal positive V/I/OVP/OCP and record all four settings plus Output.
5. D062 preview is fully read-only.
6. Successful takeover changes edge/software ownership only; Output/V/I/OVP/OCP remain unchanged through positive ACK and post-ACK TOCTOU.
7. A pre-command race/reject leaves external Output/settings untouched.
8. An actually ambiguous command/ACK enters verified-OFF containment.
9. Out-of-band increases and loss of required managed evidence force verified OFF.
10. Downward authority changes ratchet only downward and restart the fresh Delta epoch.
11. Prior-age accounting is checked against a known external start time and cannot shrink across repeated Recorder reads.
12. `MIX_TIMEOUT` physically drives and proves OFF at the chemistry active-time boundary when no hold was started.
13. A finish hold started before the boundary may complete after it and ends in verified OFF.
14. Process kill/restart while `MIX_ADOPTED` never resumes HV authority and completes verified-OFF containment.
15. No successful or failure path silently enters SAFE_WAIT/Storage or turns Output ON.

The 900 s watchdog itself has already been physically proven before and after edge D061 adoption. Because the 2026-09-03 correction does not alter `rd6018_safety_lease.yaml` or TTL timing, do not repeat a 900 s endurance wait solely for this source-heartbeat/HMI change.

Until the remaining gates pass, D062/D063 status is **software-contract PASS only**; managed-Mix physical takeover is not yet validated.
