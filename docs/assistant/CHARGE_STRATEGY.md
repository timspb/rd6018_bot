# Charge Strategy Reference

Этот документ — короткий source of truth по текущей production-стратегии V2.

Порядок проверки: `V2_DECISION_LOG.md` -> `V2_OPEN_QUESTIONS.md` -> этот документ -> `PB_RECOVERY_V2.md` -> `V1_BEHAVIORAL_AUDIT.md`.

## Главная модель

Для автоматических программ независимы:

- chemistry: AGM / EFB / Ca/Ca / Flooded;
- intent: Normal / Recovery / Conditioning / Diagnostic;
- condition: состояние конкретной АКБ;
- stage: Prep / Main / Desulfation / Mix / SAFE_WAIT / Cooling / Done.

`MANUAL` — отдельный authority mode, а не разновидность chemistry FSM.

## Production authority

- `ProductionChargeControllerV2` владеет автоматической Pb-логикой.
- Legacy `ChargeController` пока остаётся scaffold для части зрелых mechanics, но его конфликтующие Main/Mix decisions маскируются V2 authority.
- `ProductionManualSessionManager` владеет ручным режимом и не запускает автоматические Pb transitions.
- `V2RuntimeSafetyGuard`/edge lease/readback — независимая неотключаемая аппаратная граница над обоими режимами.

## Сигналы

- `battery_voltage` — батарейное U для chemistry/diagnostics;
- RD output voltage — hardware/output сигнал;
- `temp_ext` — температура АКБ;
- `temp_int` — температура RD6018/БП;
- Vin — PSU-health telemetry, не Pb-FSM authority;
- CV: U controlled, I response -> `Imin -> ΔI`;
- CC: I controlled, U response -> `Vmax -> ΔV`;
- `BAT_MODE` — наблюдение за физическим состоянием RD, не software permission.

## Аппаратная граница

Различать:

1. commanded setpoint;
2. configured/readback setpoint;
3. measured physical value.

Managed Output enable:

```text
fresh telemetry
-> envelope validation
-> OVP/OCP
-> V/I
-> readback verify
-> Output ON
-> post-enable verify
-> edge safety lease/watchdogs
```

Любая непроверяемая ошибка -> fail closed. Absolute working-voltage ceiling V2 = **17.5 V**; stage/recipe ceiling может быть ниже.

## AUTO targets

Global stage-current ceiling: 12 A.

### PREP
- ~12.0 V + temp compensation;
- ~0.01 C;
- при `Vbat < ~12 V` ток остаётся маленьким.

Прямой старт в Main при initial >=12 V всё ещё Q001.

### Main
- ~0.1 C, max 12 A;
- Ca/Ca 14.7 V;
- EFB 14.8 V;
- AGM 14.4 -> 14.6 -> 14.8 -> 15.0 V.

### Intermediate recovery / Desulfation
- 16.3 V base;
- ~0.02 C;
- 2 h;
- промежуточная recovery attempt, не final Mix.

### Mix
- Ca/Ca 16.5 V;
- EFB 16.5 V;
- AGM 16.3 V;
- ~0.03 C, max 12 A.

### Done / Storage
Normal completion:

```text
SAFE_WAIT -> Done/Storage -> ~13.8 V / 1.0 A -> Output ON
```

Fault/hard-stop — отдельная OFF-семантика.

## Temperature compensation

```text
V_comp = V_base + k * (25 - temp_ext)
```

- Ca/Ca, EFB: 0.018 V/°C;
- AGM: 0.016 V/°C;
- legacy correction clamp ~±0.60 V;
- после расчёта всегда применить recipe/absolute envelope.

Manual V является прямой операторской рабочей уставкой; автоматическая chemistry temperature compensation не должна неожиданно менять её. Thermal safety всё равно действует.

## Main evidence

Normal tail и stuck plateau — разные механизмы.

V1 baseline normal tail:
- Ca/EFB: CV + ~I<0.30A, 3h без нового минимума;
- AGM: CV + ~I<0.20A, 2h, staged Main.

Stuck plateau:
- Ca/EFB исторически ~40m flat CV plateau;
- AGM ~2h;
- плавное падение тока = progress, не plateau.

Universal `>~1%C => HV veto` отклонён. High current — только один diagnostic signal среди U/I/T/regulation/cell evidence.

## Recovery budget

Ca/EFB:

```text
plateau -> recovery #1 -> Main
later plateau -> recovery #2 -> Main
later plateau -> recovery #3 -> Main
next confirmed plateau -> final Mix
```

Progress не обнуляет count; новая charging session обнуляет. AGM policy остаётся отдельной, Q009.

## Main hard timeout

Legacy Ca/EFB ~72h fallback считается намеренным behavior, а не найденным defect. Его interaction с V2 intent — Q008.

## Mix

После target change ~120s blanking.

CV: Imin -> confirmed ΔI rise, ориентир `max(0.03A, 30%*Imin)`.

CC: Vmax -> confirmed ΔV fall, ориентир ~0.03V.

Нужно 3 spaced confirmations (~minute-class). После подтверждения запускается sticky 2h finish hold; hard safety всегда выше.

Fallback maxima:

| Chemistry | Max Mix fallback |
|---|---:|
| Ca/Ca | 20 h |
| EFB | 24 h |
| AGM | 10 h |

Это не ETA. Активный valid 2h finish hold не стирается crossing fallback boundary.

## SAFE_WAIT

После HV Output OFF:

```text
relax threshold reached early -> continue immediately
otherwise -> wait max ~2h -> continue anyway
```

2h — anti-stall maximum, не fault timeout. Relaxation остаётся diagnostic evidence.

## Cooling

Cooling — pause active chemistry/program time.

AUTO:
- Output OFF;
- exact source stage/target preserved;
- stage/tail/finish clocks frozen;
- recovery budget, AGM step, established extrema and confirmed sticky delta preserved;
- stuck plateau and incomplete delta confirmations invalidated;
- durable restore required.

MANUAL использует тот же принцип: >=40°C -> OFF/Cooling, <=35°C -> safe re-enable exact same V/I, >=45°C -> terminal stop. Active Manual timer freezes during Cooling; unfinished exact-reach/delta continuity starts fresh after resume.

## MANUAL

Manual — полноценный режим управления, не debug escape hatch и не legacy `Idle + Output ON`.

Operator owns:
- working V;
- working I;
- optional active-time timer;
- V>= / V<= / V=reach stop conditions;
- I>= / I<= / I=reach stop conditions;
- optional mode-aware delta stop;
- metadata/battery identity where useful.

Operator does **not** own OVP/OCP:

```text
OVP = target V + protection margin
OCP = target I + protection margin
```

и не может их ослабить.

Limits:
- `0 < V <= 17.5 V`;
- `0 < I <= 12 A`;
- >17.5V command is rejected before hardware enable.

Manual normal completion is defined only by operator stop conditions. Automatic Pb rules such as plateau->Recovery, tail->Mix, chemistry timeout->stage change, Done/Storage do not execute.

Every Manual start uses the same transactional safe-enable/readback/edge-lease boundary as automatic charging. Active Manual reconfiguration deliberately performs verified Output OFF and a fresh safe-enable; raw live setpoint mutation is not a supported production authority path.

Persisted active Manual after process restart becomes `INTERRUPTED`; it is **not** silently re-energized. Fresh operator re-authorization is required.

Current V2 menu exposes native Manual input and the full 17.5V envelope. Historical direct `V I` and `V I third-condition` text commands are intercepted before the legacy catch-all handler and become managed Manual sessions; third-token `15V`/`1.0A` keeps exact reach/crossing semantics. The old five-step Custom dialog remains only a stale-message/rollback compatibility adapter whose final action also enters Manual authority. Optional saved-battery binding and interrupted-session review UX remain Q002.

The persistent legacy Manual-OFF overlay remains an independent operator kill system. During a managed Manual session its conditions are also observed by the Manual manager so a physical Output OFF cannot leave Manual logically ACTIVE. Its interaction with automatic profiles remains Q003.

## Battery diagnostics / Bank Fault

V1 one-score `bank_fault` is evidence, not proof. V2 separates hypotheses:

- cell fault;
- self-discharge;
- sulfation/poor acceptance;
- stratification;
- capacity loss;
- abnormal thermal behavior;
- charger/path problem.

Diagnostics may actively request/perform bounded tests only in a safer/equal-energy direction. Do **not** raise HV merely to test a hypothesis.

### Per-cell specific gravity

For accessible flooded cells V2 stores:
- six positional cell slots;
- raw SG (never destroy original with guessed correction);
- measurement temperature;
- timestamp/context/source/notes;
- explicit missing cells.

Telegram V2 can record this evidence against a saved physical battery. SG dialog ownership outranks the global numeric Manual parser, because a six-cell numeric SG payload must never be interpreted as `V I`.

Current conservative interpretation: complete six-cell spread >=0.030 -> imbalance/stratification evidence, not “shorted cell” and not an automatic equalization veto. Persistent imbalance after corrective equalization/retest plus independent evidence can contribute to a cell-fault HV veto.

### RD6018 resistance-related evidence

Displayed `V/I` is **not battery internal resistance**.

A controlled current reduction can yield:

```text
dynamic_loop = ΔV_BAT / ΔI
```

but with the normal black+green two-wire charging path this includes battery, cables, contacts, internal path and polarization. Store/label it only as dynamic two-wire loop response. Direct trend comparison requires unchanged connection identity.

The fail-closed probe executor exists: it only lowers an existing current target, samples U/I, restores the exact prior current, and forces Output OFF if restoration/readback cannot be proven. Automatic probe trigger/amplitude/window policy is intentionally disabled until Q005/Q014 are calibrated on the physical RD path.

### Diagnostic authority

A new automatic HV escalation may be vetoed only by strong cell-fault evidence: explicit external confirmation or high-confidence independent multi-signal evidence. One heuristic score, one SG sample or one U/I point cannot. Diagnostic inference itself does not produce a hard safety stop; immediate unsafe U/I/T/protection remains the separate hard-safety layer. Calibration remains Q004/Q013.

## Physical battery registry

Longitudinal evidence binds to physical battery identity: chemistry/Ah, manufacturer/model, condition/history, capacity/CCA/external Ri if available, recovery traces, SG and dynamic-loop probes. Prefer compare-with-self trends over universal one-number judgments.

## RD health context

Model/serial/firmware and read-only calibration fingerprint are diagnostic context. `Boot Power`/`Take Out` auto-energizing is incompatible with managed charging when exposed. Changes to hardware/firmware/calibration invalidate old precision baselines.

## Watchdogs

Preserve invariant:

```text
higher-energy state -> shorter allowed blind-operation interval
```

Readback, verified OFF and local edge lease are part of safety, not chemistry.

## AI boundary

Deterministic controller owns hardware. AI explains evidence only; it cannot authorize HV, choose setpoints or override safety.

## Operator/documentation rules

- Не называй current `Imin`, пока analyzer реально не сформировал minimum evidence.
- CV: `Imin -> ΔI`; CC: `Vmax -> ΔV`.
- Не называй fallback-window ETA полного заряда.
- Не считай SAFE_WAIT timeout fault сам по себе.
- Не считай высокий ток или SG imbalance в одиночку доказательством shorted cell.
- Не путай Done/Storage с Output OFF.
- Не называй RD `V/I` или two-wire `ΔV/ΔI` внутренним сопротивлением АКБ.
- Vin/temp_int не являются battery chemistry evidence.
- Если вопрос находится в `V2_OPEN_QUESTIONS.md`, не додумывай решение по памяти.
