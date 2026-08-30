# RD6018 Telegram Operator HMI Specification

Status: **DESIGN CONTRACT — NOT YET IMPLEMENTED**

This document defines the operator-facing HMI contract for the RD6018/Pb Recovery V2 controller. It is intentionally separate from controller strategy. `V2_DECISION_LOG.md` remains the authority for charging behavior; this document defines how that behavior is presented and controlled by a human operator.

The implementation must not infer new charging authority from this document. The HMI may expose only actions already authorized by the production controller/safety boundary.

---

## 1. Design objective

The primary Telegram interface is an **operator station**, not a developer dashboard and not a database browser.

At any moment the primary panel must let the operator answer, with minimal reading:

1. **What is happening now?**
2. **What battery/program is under control?**
3. **Is the physical output ON, OFF, or unconfirmed?**
4. **Is the process healthy or does it require attention?**
5. **What, if anything, should the operator do next?**

Everything else is secondary detail.

The design optimizes for:

- situational awareness;
- low cognitive load;
- clear command/result feedback;
- minimal chance of accidental unsafe action;
- explicit degraded/unknown states;
- mobile operation with one hand;
- Telegram-native resilience when optional web UI is unavailable.

---

## 2. Research basis

The design uses the following external principles as guidance, adapted to one RD6018 charger rather than copied mechanically from a plant DCS.

### 2.1 HMI hierarchy / task-centered design

ISA high-performance HMI guidance separates displays into an overview, routine-operation display, detail/troubleshooting display, and transient control/faceplate level. The practical principle adopted here is:

> Show routine operating context at the main level; expose diagnostic internals only when the operator asks for them or when an abnormal state makes them relevant.

References:

- ISA, *How DCS Migration Improves Operator Experience*: https://www.isa.org/intech-home/2023/april-2023/features/how-dcs-migration-improves-operator-experience
- ISA, *The Four Pillars of Operator Performance*: https://www.isa.org/intech-home/2023/2023-february-2023/features/four-pillars-operator-performance
- HSE, *Control room design*: https://www.hse.gov.uk/comah/sragtech/techmeascontrol.htm

### 2.2 Command feedback and alarms

HSE guidance is adopted directly as a human-factors principle:

- after an operator action, show its result;
- if the result is delayed, explicitly show that the command is still pending;
- deviations from safe operation must be conspicuous;
- an alarm should state the reason and required response;
- alarm coding must not depend on color alone;
- avoid alarm flooding.

Reference:

- https://www.hse.gov.uk/comah/sragtech/techmeascontrol.htm

### 2.3 Telegram platform

As of Bot API 10.3 (24 August 2026), Telegram Rich Messages support structured content including headings, tables, collapsible/detail blocks and in-message buttons; Rich Message buttons support semantic styles such as `primary`, `success`, `danger` and `link`.

References:

- Bot API: https://core.telegram.org/bots/api
- Bot Features / Rich Messages: https://core.telegram.org/bots/features

This capability is new. **The initial production migration must keep a classic HTML + InlineKeyboard fallback until rendering/interaction has been verified on the actual Android/Desktop clients used for this charger.**

Telegram Mini Apps remain useful for dense analysis/history. Telegram requires responsive mobile-first design and supplies theme/safe-area information.

Reference:

- https://core.telegram.org/bots/webapps

The Mini App is explicitly **not** the sole safety control path.

---

## 3. HMI level model

For this project the conventional HMI hierarchy is mapped as follows.

### L1 — asynchronous attention

Purpose: make the operator notice a meaningful abnormal/change condition without opening the bot dashboard.

Examples:

- hardware trip;
- battery overtemperature pause;
- OFF unconfirmed;
- communication loss that caused a protective OFF;
- program completion if requested;
- operator action required.

L1 is delivered as a concise Telegram notification/message.

**L1 is not the event log.** Routine events must not generate alarms.

### L2 — primary operator panel

Purpose: normal monitoring and routine Start/Stop/navigation.

The operator should be able to understand L2 in approximately one glance.

L2 contains:

- battery/program identity;
- process state/stage;
- physical Output state;
- key live U/I/P/T values;
- target/progress in human terms;
- one compact safety/communications status;
- at most one primary process action plus a small number of navigation actions.

L2 does **not** normally contain:

- raw `decision` enum;
- `authoritative=True/False` developer wording;
- every Imin/Vmax/Δ threshold;
- calibration fingerprint;
- raw HA entity names;
- complete OVP/OCP/readback details;
- full event log;
- battery diagnostic hypothesis scores;
- three permanently visible graph range selectors.

### L3 — detail / troubleshooting workspace

Purpose: explain why the controller is doing what it is doing.

Examples:

- current stage evidence;
- CV/CC-specific Imin/Vmax/Δ evidence;
- targets and protection readback;
- graph/trends;
- events;
- communications diagnostics;
- battery history;
- SG/diagnostic evidence.

### L4 — transient action / confirmation

Purpose: operator input that temporarily takes focus and then disappears.

Examples:

- Start preview and confirmation;
- normal Stop confirmation;
- Manual V/I entry;
- Manual-OFF condition entry;
- battery registration/edit form;
- SG input;
- re-authorize interrupted Manual.

L4 must return to a meaningful L2/L3 state after completion or cancellation.

---

## 4. Presentation must be derived from a semantic HMI state

The renderer must not continue scraping arbitrary controller attributes directly.

Introduce a presentation DTO (name illustrative):

```python
OperatorHmiState(
    process_state=...,          # IDLE/STARTING/RUNNING/PAUSED/STOPPING/STORAGE/TRIPPED/CONTAINMENT/INTERRUPTED
    authority=...,              # NONE/AUTO/MANUAL/CONTAINMENT
    stage=...,                  # PREP/MAIN/RECOVERY/MIX/SAFE_WAIT/COOLING/STORAGE/MANUAL/...
    regulator=...,              # CC/CV/UNKNOWN
    attention=...,              # NORMAL/ADVISORY/WARNING/ALARM/TRIP
    output_state=...,           # ON/OFF/UNKNOWN
    battery=...,
    program=...,
    telemetry=...,
    target=...,
    progress=...,
    command=...,
    communications=...,
    operator_action=...,
)
```

The exact Python shape is implementation detail, but the separation is normative.

### 4.1 Why this boundary exists

The current UI knows too much about internal FSM implementation. That creates three risks:

1. internal refactors silently change operator wording;
2. presentation code can accidentally reproduce stale legacy semantics;
3. the main panel becomes a debug dump instead of decision support.

The controller/domain layer owns the truth. The HMI adapter converts it to stable operator semantics. Renderers then render that semantic state.

---

## 5. Canonical process states

The operator layer must distinguish the following top-level states even when several map to existing controller stages internally.

### `IDLE`

- Output confirmed OFF;
- no managed session;
- ready for new program if safety preconditions are available.

### `STARTING`

A start was authorized, but physical ON has not yet been fully verified.

Must show command progress such as:

```text
Запуск...
Уставки записаны
Проверка readback
Ожидание подтверждения Output ON
```

Do not say “заряд запущен” before the transaction is physically verified.

### `RUNNING`

Managed AUTO or Manual output is ON and runtime safety is healthy.

### `PAUSED`

Managed process deliberately has Output OFF but retains continuation authority.

Examples:

- Cooling;
- SAFE_WAIT.

`PAUSED` must not look like ordinary idle.

### `STOPPING`

OFF has been commanded but not yet confirmed.

This is a **command-in-progress state**, not success.

### `STORAGE`

Completed normal program holding the battery at Storage/float with Output ON.

Do not label Storage as generic “Done” if that could imply Output OFF.

### `TRIPPED`

A confirmed hardware/safety trip caused protective action.

### `CONTAINMENT`

The controller cannot prove safe physical OFF or another critical actuator fact. This is a high-attention state and must persist until containment is resolved.

Examples:

- `OFF unconfirmed`;
- Output state unknown after failed stop;
- safety boundary retrying verified shutdown.

### `INTERRUPTED`

A persisted Manual/diagnostic request survived restart but has no live actuator authority and requires explicit operator re-authorization or discard.

---

## 6. Attention model

Attention is independent from process stage.

### `NORMAL`

No operator action required.

Visual treatment: quiet, neutral.

### `ADVISORY`

Useful context, no immediate action.

Examples:

- rest window recommended;
- SG retest useful later;
- battery diagnostic evidence accumulating.

Advisory normally appears in detail view, not as a push notification.

### `WARNING`

Abnormal but managed condition that the operator should notice.

Example:

- Cooling with OFF confirmed and automatic resume planned.

The message must say whether action is required.

### `ALARM`

Operator attention/action is required or the process is significantly degraded.

Examples:

- required sensor unavailable;
- communication path fault preventing continuation;
- repeated safety containment issue.

### `TRIP`

Hard protection event / immediate protective action.

Examples:

- OVP/OCP/OPP;
- critical battery temperature;
- critical PSU temperature;
- absolute runtime safety violation.

### 6.1 Color and symbols

Color is a secondary cue only.

Normative rules:

- chemistry is **never** color-coded as severity;
- AGM must not be represented with a red danger square merely because it is AGM;
- red/danger is reserved for destructive/stop/trip semantics;
- green/success is reserved for confirmed completion/safe success, not routine “everything is green” decoration;
- every warning/alarm meaning is also expressed in text/symbols;
- the normal panel should remain visually quiet.

---

## 7. Alarm philosophy

Events, advisories and alarms are different objects.

### 7.1 Event

Logged only unless requested.

Examples:

- stage transition;
- target adjustment;
- checkpoint;
- Imin/Vmax update;
- lease renewal.

### 7.2 Advisory

Visible in panel/detail but normally no push.

### 7.3 Warning

One concise push when the state becomes active, plus a persistent L2 banner while active.

### 7.4 Alarm/Trip

Immediate push, persistent L2 banner, clear required action if any.

### 7.5 Alarm content template

Every warning/alarm must answer:

```text
WHAT happened?
WHAT did automation do?
WHAT is the physical Output state?
WHAT must the operator do now?
```

Example:

```text
ТЕРМОПАУЗА

АКБ: 40.2°C
Output OFF подтверждён.
Автоматика ждёт охлаждения до ≤35°C.

Действие оператора: не требуется.
```

Bad example:

```text
TEMP_PAUSE stage transition / temp=40.2
```

### 7.6 Alarm flood prevention

A single causal incident must not create a burst of equivalent push messages.

For example:

```text
sensor stale -> protective off -> session frozen -> communication warning
```

should normally be rationalized into one operator alarm with secondary events retained in the log.

---

## 8. Main L2 panel information hierarchy

### Priority A — state and physical truth

Always visible:

- battery/program identity;
- process state/stage;
- Output ON/OFF/UNKNOWN;
- active warning/alarm/containment banner.

### Priority B — current process values

Normally visible:

- `Vbat`;
- current;
- battery temperature;
- optionally power where useful;
- PSU temperature in compact form.

### Priority C — target/progress

Visible in semantic form:

- target V/current limit;
- CC/CV mode when confirmed;
- qualitative progress such as:
  - `Ток снижается`;
  - `Формируется Imin`;
  - `Δ подтверждена · выдержка 43м / 2ч`;
  - `Ожидание релаксации`;
  - `Охлаждение до ≤35°C`.

### Priority D — health summary

One compact line or block:

```text
Защита: норма
Связь: RD ✓  ESP ✓  HA ✓
```

If abnormal, the summary becomes the abnormal banner rather than adding another unrelated line.

### Priority E — deep evidence

L3 only unless it directly explains an active alarm.

---

## 9. L2 control hierarchy

### Active managed process

Maximum preferred controls on L2:

```text
[ Остановить заряд ]
[ Подробнее ]
[ График ] [ Ещё ]
```

Semantics:

- `Остановить заряд` — destructive/danger;
- `Подробнее` — primary navigation;
- `График` — secondary navigation;
- `Ещё` — secondary menu for low-frequency functions.

Do not permanently place graph range selectors, battery registry, event log, controller details and diagnostics as peers of Stop.

### Idle

Preferred controls:

```text
[ Новая программа ]
[ Ручной режим ] [ График ]
[ АКБ ]          [ Ещё ]
```

`Условие OFF` belongs under Manual/More, not as a permanent top-level control when it is not armed.

### Paused / containment

Primary control is determined by state, not by generic power toggle.

Examples:

- Cooling: `Подробнее`, possibly `Остановить программу`; **no “resume now” bypass**;
- OFF unconfirmed: no Start and no reconfiguration controls; containment status + retry owned by safety layer;
- SAFE_WAIT: `Остановить программу`, `Подробнее`; no arbitrary ON button.

---

## 10. Start interaction contract

A normal start is a deliberate L4 workflow.

Preferred path for registered batteries:

```text
New Program
  -> select physical battery
  -> select program/intent
  -> preview
  -> explicit START
  -> STARTING
  -> verified RUNNING
```

Ad-hoc path:

```text
New Program
  -> Other battery
  -> chemistry
  -> Ah
  -> program/intent
  -> preview
  -> START
```

### 10.1 Program labels

Operator wording must match the actual V2 contract.

#### Normal / `Обычный заряд`

**Full automatic standard charge.** It may use the standard recovery/Mix chain when deterministic V2 criteria call for it.

It must never again be described as “without automatic HV/Mix”.

#### Recovery / `Восстановление`

An explicit recovery-oriented program. Standard HV recovery may be used only within recipe and diagnostic authority.

#### Conditioning / `Кондиционирование`

Service/conditioning intent inside the approved recipe envelope. It is not an unrestricted expert-voltage mode.

#### Diagnostic / `Диагностика`

Observation/diagnostic intent with no new automatic HV escalation.

#### Auto Mix / `Авто Mix`

Direct Mix entry without PREP/Main/intermediate Recovery; `<12.0 V` start is rejected rather than silently falling back to PREP.

### 10.2 Preview requirements

Preview must show only decision-relevant facts by default:

- battery identity/chemistry/Ah;
- selected program;
- entry stage;
- normal target/maximum relevant target;
- current ceiling;
- whether standard Mix/HV is possible;
- battery temperature;
- readiness/safety state;
- current physical Output state.

Detailed explanation belongs in a collapsible/details section or secondary screen.

### 10.3 Start result

The UI must not report success at command submission.

State progression:

```text
START requested
-> STARTING
-> readback/lease/output verification
-> RUNNING
```

If enable fails but OFF is confirmed:

```text
Запуск не выполнен.
Output OFF подтверждён.
Причина: ...
```

If OFF cannot be confirmed:

```text
ЗАПУСК ПРЕРВАН
Состояние Output не подтверждено.
Контур выполняет защитное отключение.
```

and the UI enters `CONTAINMENT`.

---

## 11. Stop interaction contract

### 11.1 Normal operator stop

A normal Stop from a healthy running session may use confirmation:

```text
Остановить текущую программу?
MAIN · 14.62 V · 2.14 A
```

Actions:

```text
[ ОСТАНОВИТЬ ]
[ Продолжить ]
```

### 11.2 No confirmation for safety shutdown

Safety-triggered OFF is automatic and never waits for Telegram confirmation.

### 11.3 Stop command lifecycle

After operator confirms Stop:

```text
STOPPING
Команда OFF отправлена.
Ожидание подтверждения RD6018...
```

Only after proof:

```text
Заряд остановлен.
Output OFF подтверждён.
```

If proof is absent:

```text
OFF НЕ ПОДТВЕРЖДЁН

Команда отключения отправлена, но физическое состояние RD6018 не подтверждено.
Защитный контур продолжает попытки отключения.

Не отключайте питание/связь с контроллером без необходимости.
```

No new Start/setpoint action is exposed in this state.

---

## 12. Stage-specific operator semantics

### PREP

Show:

- `Подготовка`;
- low-current charge;
- reason in operator terms: low initial battery voltage;
- current target and transition criterion if useful.

Do not expose implementation constants unless Detail is opened.

### MAIN

Show:

- `Основной заряд`;
- CC/CV mode;
- current target/current limit;
- qualitative progress.

Do not show raw plateau counters on L2.

### Recovery / Desulfation

Use a neutral but explicit label such as:

```text
Восстановительный этап
16.3 V · ограниченный ток
```

Do not imply guaranteed “desulfation success”.

### MIX

Show mode-specific semantic evidence:

- CV: current behavior;
- CC: voltage behavior;
- once confirmed: `Финишный критерий подтверждён` and sticky-hold progress.

### SAFE_WAIT

Must clearly say:

```text
Безопасное ожидание
Output OFF
Наблюдение релаксации
```

This must never look like idle or fault unless diagnostics actually raised one.

### COOLING

Must clearly say:

```text
Термопауза
Output OFF подтверждён
АКБ X°C -> ждём ≤35°C
```

If automatic resume is expected, say so.

### STORAGE

Must clearly say Output remains ON:

```text
Заряд завершён · Хранение
13.8 V / 1.0 A
Output ON
```

Never present `DONE` alone.

---

## 13. Manual HMI contract

Manual is a supported product mode, not a hidden developer tool.

### Start

Show operator-owned:

- V;
- I;
- derived OVP/OCP;
- optional battery identity for history only;
- stop conditions.

The preview must explicitly distinguish:

```text
Задано оператором: V/I
Рассчитано системой: OVP/OCP
```

### Active

L2 must identify `Ручной режим` distinctly from AUTO.

### Cooling

Show that Manual program is paused and the same requested V/I will be restored only after thermal criteria and the fresh safe-enable transaction.

### Restart

An interrupted request is not an active Manual session.

Display:

```text
Прерванный Manual
Output не будет включён автоматически.
```

Actions:

```text
[ Проверить и запустить заново ]
[ Удалить запрос ]
```

---

## 14. Auto Mix HMI contract

Auto Mix must be presented as a separate program, not as a chemistry or intent synonym.

Preview must explicitly state:

```text
Старт сразу с Mix
PREP/Main/Recovery пропускаются
Минимальный Vbat для старта: 12.0 V
```

Show standard chemistry target:

- AGM: 16.3 V;
- EFB/Ca/Flooded: 16.5 V;
- current around standard Mix recipe (~0.03C subject to hardware cap).

Do not mention or imply EFB expert 17.2–17.5 V capability.

---

## 15. Diagnostic HMI

Diagnostic is split into two surfaces.

### Operator summary

Human result:

```text
Диагностика
Автоматический HV запрещён
Наблюдение продолжается
```

or, when evidence warrants:

```text
Требуется проверка
Причина: устойчивый побаночный дисбаланс после corrective cycle
```

### Technical detail

May include:

- hypotheses;
- scores/levels;
- supporting/counter evidence;
- SG measurements;
- rest observations;
- dynamic-loop descriptive evidence;
- calibration status.

The technical view must continue to say that diagnostic inference does not create a physical HARD_STOP by itself.

---

## 16. Battery registry HMI

A registered battery is an operator object, not just a database row.

Card summary:

```text
Varta Silver Dynamic
AGM · 70 Ah
Состояние: ...
Последний цикл: ...
```

Primary actions:

```text
[ Зарядить ]
[ История ]
[ Диагностика ]
[ Изменить ]
```

Do not mix registration/edit fields into the normal start screen unless needed.

Chemistry is descriptive text, not severity color.

---

## 17. SG workflow

SG belongs to L3/L4 diagnostics, never to the routine main panel.

Rules from D053 remain authoritative:

- AGM: no SG prompt;
- electrolyte access must be explicitly `SERVICEABLE` for applicable batteries;
- six cell positions remain explicit;
- inaccessible cell is not treated as zero/bad;
- raw is primary evidence;
- correction metadata is explicit;
- a temperature-compensated hydrometer is not corrected twice.

For six-cell input, a Mini App may eventually be preferable, but native Telegram must retain a usable fallback.

---

## 18. Graph workspace

The graph is L3, not permanent L2 navigation clutter.

Opening `График` exposes:

```text
[ 30 мин ] [ 2 часа ] [ Сессия ]
```

Recommended graph content:

- Vbat;
- current;
- battery temperature;
- optional setpoint overlays;
- stage markers;
- Cooling/SAFE_WAIT/Recovery/Mix markers;
- warning/trip markers.

The graph should answer “how did we get here?” and “what is the trend?”, not duplicate exact current values already shown on L2.

---

## 19. Events workspace

The event log must support diagnosis without becoming an alarm stream.

Preferred default view:

- meaningful program transitions;
- warnings/trips;
- operator actions;
- startup/stop result;
- persistence/restart events.

Verbose evidence/checkpoint events belong under an expanded technical filter.

---

## 20. Communications/health display

L2 normal summary:

```text
Связь: RD ✓  ESP ✓  HA ✓
```

If one component is degraded, replace the neutral summary with the causal condition.

Examples:

```text
HA telemetry stale · Output OFF
```

```text
Edge lease lost · Output OFF подтверждён
```

Do not expose raw entity names on L2.

L3 diagnostics may expose source timestamps, age, skew, entity IDs, lease generation and readback details.

---

## 21. Telegram message ownership

The current timeline-management approach should evolve toward **one logical operator panel per chat**, edited in place whenever Telegram/client behavior permits.

### Requirements

- asynchronous alarms may be separate messages so they create attention;
- the persistent L2 panel should not be reposted after every nested navigation click;
- L3/L4 workspaces may be separate temporary messages/cards;
- returning from workspace must provide an obvious `К панели` path;
- old stale action cards should be retired/disabled/expired where possible;
- callback handling must reject stale session/start previews instead of acting on obsolete state.

The HMI renderer must never convert a successful actuator command into a failure merely because message editing/rendering failed.

---

## 22. Rich Message migration

Rich Messages are the preferred future native renderer because they can provide structure without a Mini App.

### Candidate Rich Message features

- heading for state/battery;
- compact table for primary process values;
- divider;
- details/collapsible technical explanation;
- semantic button styles;
- in-document sections for detail views.

### Safety constraints

- do not place safety-critical buttons inside experimental table-cell interactions;
- Start/Stop must remain in a simple tested button row;
- do not rely on a new client feature until the actual Android/Desktop clients have been verified;
- preserve classic HTML + InlineKeyboard fallback.

### Migration phases

1. **Client capability/render spike** — no production dependency.
2. Rich message body with classic keyboard fallback.
3. Rich semantic button rows after interaction verification.
4. Optional richer detail screens.
5. Remove fallback only if there is a compelling reason and client support is proven; default expectation is to keep it.

---

## 23. Mini App boundary

A Mini App is a **secondary analytical console**, not the only operator station.

Good Mini App use cases:

- interactive graphs;
- battery registry/history;
- longitudinal capacity/CCA/SG views;
- event filtering;
- multi-cell SG forms;
- diagnostic evidence exploration;
- calibration trace review.

Native Telegram must continue to provide:

- current state;
- alarms;
- Start;
- Stop;
- containment status;
- basic program selection.

If the Mini App is down, the charger remains fully stoppable and understandable from native Telegram.

---

## 24. Confirmation rules

Confirmation is not uniformly good.

### Require confirmation

- normal operator Stop of a healthy active program;
- Start after preview;
- destructive deletion of battery/history data;
- re-authorization of interrupted Manual;
- any future expert/model-specific exceptional recipe.

### Do not require confirmation

- automatic safety OFF;
- hard trip containment;
- navigation;
- refresh;
- acknowledge/read advisory;
- safe cancellation before an actuator command has started.

---

## 25. Stale interaction policy

Every L4 action card that can start/reconfigure hardware must carry enough semantic identity to detect staleness:

- user/chat;
- battery identity;
- intended program;
- generation/session token or equivalent;
- current controller state.

If stale:

```text
Эта карточка устарела.
Откройте программу заново.
```

Never silently reuse an old preview against a newly connected/different battery/session.

---

## 26. Accessibility and wording

### Wording

Use Russian operator language first. Internal English terms may appear in technical detail when they are the actual domain name.

Preferred:

```text
Основной заряд
Термопауза
Безопасное ожидание
Финишная выдержка
Состояние Output не подтверждено
```

Avoid on L2:

```text
authoritative
legacy scaffold
recipe envelope
transition audit
v2_internal_error
```

### Units

Keep stable formatting:

- voltage: `14.62 V`;
- current: `2.14 A`;
- temperature: `27.4°C`;
- capacity: `70 Ah`;
- time: `1ч 42м`.

### Icons

Icons supplement words; they do not replace them.

Use a very small stable vocabulary:

- `▶` Start;
- `■/STOP` or explicit text for Stop;
- `⚠` Warning;
- `🚨` Trip/critical only if visually useful;
- `✓` confirmed result;
- `?`/text for unknown where necessary.

Avoid decorative colored chemistry icons.

---

## 27. Primary-panel acceptance criteria

A design does not pass review unless all are true:

1. A new operator can identify Output state without opening Detail.
2. `Storage` cannot be mistaken for Output OFF.
3. `SAFE_WAIT` cannot be mistaken for idle.
4. `OFF unconfirmed` cannot be mistaken for successful stop.
5. Normal, Recovery, Diagnostic and Auto Mix wording matches actual V2 authority.
6. No normal chemistry uses danger color merely as identity.
7. Start success is shown only after physical verification.
8. Stop success is shown only after verified OFF.
9. A safety alarm states automation response and required operator action.
10. Main panel contains no more than one dominant process action.
11. Technical evidence remains reachable in at most one additional navigation level.
12. Mini App failure cannot remove native Stop/status capability.
13. Renderer failure cannot change actuator result/authority.
14. Old/stale preview buttons cannot start a new session silently.
15. The panel remains usable in classic Telegram rendering if Rich Message support is unavailable or disabled.

---

## 28. Implementation architecture target

Recommended eventual module split:

```text
controller / runtime / safety
           |
           v
operator_hmi_state.py
  semantic state adapter
           |
           +-------------------+
           |                   |
           v                   v
telegram_rich_renderer.py   telegram_html_renderer.py
           |
           v
Telegram callbacks -> command/application boundary -> safety transaction
```

Optional later:

```text
operator_hmi_state.py
           |
           v
mini_app_api.py
```

### Critical rule

**Renderers do not own actuator sequencing.**

A callback such as `start`, `stop`, `manual_apply`, or `auto_mix_start` invokes the existing application/safety command boundary. The renderer only displays pending/result states.

---

## 29. Explicit non-goals for first HMI migration

Do not combine the redesign with:

- changing charge thresholds;
- changing recovery budgets;
- changing diagnostic score thresholds;
- enabling automatic diagnostic probes;
- implementing EFB >16.5 V automatic recipes;
- making the Mini App mandatory;
- introducing private-chat topics as a navigation dependency.

HMI migration must be behavior-preserving except for correction of demonstrably false/stale operator wording.

---

## 30. Required pre-implementation review

Before writing the new renderer, review `OPERATOR_HMI_WIREFRAMES.md` screen by screen for at least these scenarios:

- IDLE / healthy;
- normal program selection and Start;
- STARTING;
- PREP;
- MAIN CC;
- MAIN CV;
- Recovery;
- MIX before finish evidence;
- MIX sticky finish hold;
- SAFE_WAIT;
- Cooling;
- Storage;
- normal operator Stop;
- STOPPING;
- OFF unconfirmed containment;
- hardware trip;
- stale/missing telemetry protective stop;
- Manual start/active/cooling/stop;
- interrupted Manual re-authorization;
- Auto Mix;
- Diagnostic;
- battery registry;
- SG input/retest;
- graph/detail/events.

Implementation begins only after the storyboard is accepted.
