# Charge Strategy Reference

Этот документ — короткий source of truth по текущей production-стратегии V2.

Порядок проверки: `V2_DECISION_LOG.md` -> `V2_OPEN_QUESTIONS.md` -> этот документ -> `PB_RECOVERY_V2.md` -> `V1_BEHAVIORAL_AUDIT.md`.

## Главная модель

Для автоматических программ независимы chemistry, intent, condition, entry/program mode и stage. `MANUAL` — отдельный authority mode, а не разновидность chemistry FSM.

### Intent

- **Normal** — штатный полный автоматический заряд, V1-compatible: промежуточный recovery и финальный Mix разрешены только по детерминированным критериям.
- **Recovery** — тот же безопасный контур с явной восстановительной целью/диагностическим контекстом; evidence и safety не обходятся.
- **Conditioning** — сервисная программа внутри разрешённого envelope; expert EFB 17.2–17.5 V остаётся отдельным неготовым workflow.
- **Diagnostic** — наблюдение/проверка без автоматического создания Recovery/Mix.

`Auto Mix` — не intent. Это отдельный direct-entry program mode: оператор явно просит начать сразу с Mix.

## Production authority

- `AutoStrategyProductionChargeControllerV2` владеет production AUTO Main/timeout/Mix strategy поверх зрелого legacy scaffold.
- `DiagnosticProductionChargeControllerV2` добавляет hypothesis-specific HV veto перед применением выбранного HV transition.
- `v2_mix_mode` создаёт direct-entry Mix session, но не обходит controller/runtime safety authority.
- `ProductionManualSessionManager` владеет Manual.
- `V2RuntimeSafetyGuard`/readback/verified OFF/edge lease — отдельная неотключаемая аппаратная граница.

## Сигналы

- `battery_voltage` — chemistry/diagnostics;
- RD output voltage — hardware/output monitoring;
- `temp_ext` — температура АКБ;
- `temp_int` — температура RD6018/БП;
- Vin — PSU-health telemetry, не Pb-FSM authority;
- CV -> current response (`Imin -> ΔI`);
- CC -> voltage response (`Vmax -> ΔV`);
- `BAT_MODE` — observation, not software permission.

## Аппаратная граница

Различать commanded setpoint, configured/readback setpoint и measured physical value.

Managed Output enable:

```text
fresh telemetry
-> envelope validation
-> OVP/OCP
-> V/I
-> readback verify
-> edge lease
-> Output ON
-> post-enable verify
```

Непроверяемая ошибка -> fail closed. Absolute working-voltage ceiling V2 = **17.5 V**; конкретный recipe может быть ниже.

## AUTO start / PREP

Обычный полный AUTO выбирает старт **до первого Output ON**:

```text
Vbat < 12.0 V  -> PREP, ~12 V + temp compensation, ~0.01C
Vbat >= 12.0 V -> MAIN сразу + PREP_SKIPPED audit event
```

Это устраняет V1-состояние “логически PREP, физически уже Main”. Restore не пересчитывает этот выбор: восстанавливается сохранённая stage/target semantics.

## AUTO Mix-only

`Auto Mix` — отдельная операторски выбранная автоматическая программа:

```text
operator selects Auto Mix
        -> validate Vbat/safety/diagnostics
        -> create session directly in STAGE_MIX
        -> protected/readback-verified Output enable
        -> Mix evidence/fallback
        -> SAFE_WAIT
        -> Done/Storage
```

Контракт:

- PREP не выполняется;
- Main не выполняется;
- intermediate Recovery/Desulfation не выполняется;
- `Vbat < 12.0 V` -> **reject start**, а не скрытый fallback в PREP;
- Ca/Ca/EFB -> стандартный Mix до 16.5 V;
- AGM -> стандартный Mix до 16.3 V;
- ток ~0.03C, max 12 A;
- после старта работают те же ~120 s blanking, CV `Imin -> ΔI`, CC `Vmax -> ΔV`, 3 spaced confirmations и sticky 2 h hold;
- fallback остаётся Ca20/EFB24/AGM10;
- после Mix работает обычный SAFE_WAIT -> Storage 13.8 V/1 A Output ON;
- strong `BLOCK_AUTOMATIC_HV` veto применяется **до** включения;
- readback, OVP/OCP, thermal safety, edge lease и watchdog не ослабляются;
- Auto Mix использует только standard Mix recipe envelope и **не** даёт implicit access к expert EFB 17.2–17.5 V.

То есть это «начать автоматическую программу с финального Mix», а не Manual и не новый `ChargeIntent`.

## AUTO targets

Global stage-current ceiling: 12 A.

### Main
- ~0.1 C, max 12 A;
- Ca/Ca 14.7 V;
- EFB 14.8 V;
- AGM 14.4 -> 14.6 -> 14.8 -> 15.0 V;
- temperature compensation применяется внутри разрешённого recipe envelope.

### Intermediate recovery / Desulfation
- 16.3 V base;
- ~0.02 C;
- 2 h;
- это bounded intermediate attempt, не final Mix.

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

## Main evidence

Normal tail и stuck plateau — разные механизмы.

V1-compatible tail:
- Ca/EFB: CV + I<~0.30A, 3 h continuous hold/no new minimum;
- AGM: CV + I<~0.20A, 2 h, staged Main.

Stuck plateau:
- Ca/EFB ~40 min flat CV plateau;
- AGM ~2 h;
- плавное снижение тока = progress, не plateau.

Universal `>~1%C => HV veto` отклонён. Current magnitude — лишь diagnostic evidence среди U/I/T/regulation/cell data.

## Recovery budget

### Ca/Ca / EFB

```text
plateau -> recovery #1 -> Main
later plateau -> recovery #2 -> Main
later plateau -> recovery #3 -> Main
next confirmed plateau -> final Mix
```

Три попытки — budget всей charging session; progress count не обнуляет.

### AGM

```text
plateau -> recovery #1 -> Main
...
plateau -> recovery #4 -> Main
next plateau -> remain Main, НЕ forced Mix
```

AGM budget = 4/session. После исчерпания ждём штатный low-current tail либо применяем 72 h conservative fallback. REHYDRATED не меняет transitions автоматически.

## Main 72 h fallback

72 h — **strategy fallback**, а не универсальный hard-safety timeout.

- Ca/Ca / EFB, intent Normal/Recovery/Conditioning: `Main 72h -> Mix` даже если не сформировалась фиксированная stuck plateau.
- AGM: `Main 72h -> Mix` только если уже подтверждён CV и `I <= 0.20 A`; иначе `stop + diagnose`.
- Diagnostic: `72h -> stop + diagnose`, без автоматического HV.

Production V2 скрывает реальный Main elapsed clock от legacy scaffold timeout и затем применяет это решение сам. Rollback legacy behavior остаётся воспроизводимым отдельно.

## Mix

После target change ~120s blanking.

- CV: Imin -> confirmed ΔI rise, ориентир `max(0.03A, 30%*Imin)`.
- CC: Vmax -> confirmed ΔV fall, ориентир ~0.03V.
- Нужны 3 spaced confirmations (~60s).
- После подтверждения запускается sticky 2 h finish hold; hard safety всегда выше.

Fallback maxima:

| Chemistry | Max Mix fallback |
|---|---:|
| Ca/Ca | 20 h |
| EFB | 24 h |
| AGM | 10 h |

Это не ETA. Активный valid 2h finish hold не стирается crossing fallback boundary.

## Diagnostic HV veto

Сначала strategy выбирает действие. Затем hypothesis engine может veto только **новое** `ENTER_DESULFATION`/`ENTER_MIX` при `BLOCK_AUTOMATIC_HV`.

Для direct-entry `Auto Mix` тот же veto проверяется как preflight до создания/включения HV-сессии.

Обычный transition-veto применяется одинаково к Normal/Recovery/Conditioning и timeout-generated Mix. AGM voltage-step внутри Main не считается HV escalation. Один score/SG/U/I sample veto не создаёт.

## SAFE_WAIT

После HV Output OFF:

```text
relax threshold reached early -> continue immediately
otherwise -> wait max ~2h -> continue anyway
```

2 h — anti-stall maximum, не fault timeout. Relaxation остаётся diagnostic evidence.

## Cooling

Cooling — pause active chemistry/program time.

AUTO:
- Output OFF;
- exact source stage/target preserved;
- stage/tail/finish clocks frozen;
- recovery budget, AGM step, extrema, confirmed sticky delta preserved;
- stuck plateau and incomplete delta confirmations invalidated;
- durable restore required.

Для Auto Mix source stage = Mix, поэтому Cooling возвращает ровно в Mix с теми же pause semantics.

MANUAL: >=40°C -> OFF/Cooling, <=35°C -> safe re-enable exact same V/I, >=45°C -> terminal stop. Active timer freezes; unfinished reach/delta continuity starts fresh after resume.

## MANUAL

Manual — полноценный режим управления, не debug escape hatch и не legacy `Idle + Output ON`.

Operator owns working V/I and optional timer/V/I/reach/delta stop conditions. OVP/OCP всегда derived и не могут быть ослаблены пользователем.

Limits:
- `0 < V <= 17.5 V`;
- `0 < I <= 12 A`.

Automatic Pb rules не выполняются. Every start/reconfiguration проходит через transactional safe-enable; active reconfiguration делает verified OFF -> fresh enable. Persisted active Manual restores `INTERRUPTED`, never auto-ON.

## AUTO user OFF condition

Persistent `Manual-OFF` при запущенном автоматическом профиле — только дополнительное асинхронное условие terminal OFF.

```text
AUTO chemistry FSM ---------------------> PREP/Main/Recovery/Mix/SAFE_WAIT/Storage
          |
          +---- armed user OFF condition observed in parallel
                         |
                         +---- condition not reached -> no influence on AUTO decisions
                         +---- condition reached     -> Output OFF + session STOP
```

Правила:
- сам факт вооружённого OFF не подавляет Recovery, Mix, 72h fallback или normal completion;
- он не меняет chemistry evidence/timers/authority;
- hard safety и diagnostic HV authority продолжают иметь обычный приоритет;
- при срабатывании условие означает именно terminal user-requested OFF, а не переход к `Done/Storage`;
- после такого stop V2 не должен автоматически включать Storage 13.8 V;
- production boundary не передаёт legacy `manual_off_active=True` внутрь AUTO FSM; legacy evaluator остаётся независимым side-channel до окончательного удаления старого механизма.

## Battery diagnostics / Bank Fault

V1 one-score `bank_fault` = evidence, not proof. V2 separates cell fault, self-discharge, sulfation, stratification, capacity loss, thermal abnormality, charger/path fault.

Diagnostics may perform only safer/equal-energy bounded experiments and never raise HV merely to test a hypothesis.

### SG
Store six positional cells, raw SG, measurement temperature, timestamp/context/source/notes. First complete spread >=0.030 = imbalance/stratification evidence, not “shorted cell” and not automatic equalization veto.

### RD resistance-related evidence
Displayed `V/I` is not battery internal resistance. Controlled current reduction may produce `dynamic_loop = ΔV_BAT/ΔI`, but two-wire black+green path includes battery+cables+contacts+internal path+polarization. Compare longitudinally only under an explicit unchanged connection identity.

## Watchdogs / AI

Preserve `higher-energy state -> shorter allowed blind-operation interval`. Readback, verified OFF and edge lease are safety, not chemistry. AI explains evidence only; it cannot authorize HV, select setpoints or override safety.

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
