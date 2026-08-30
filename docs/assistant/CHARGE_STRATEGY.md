# Charge Strategy Reference

Этот документ — короткий source of truth по текущей production-стратегии V2.

Порядок проверки: `V2_DECISION_LOG.md` -> `V2_OPEN_QUESTIONS.md` -> этот документ -> `PB_RECOVERY_V2.md` -> `V1_BEHAVIORAL_AUDIT.md`.

## Главная модель

Для автоматических программ независимы chemistry, intent, condition, entry/program mode и stage. `MANUAL` — отдельный authority mode, а не разновидность chemistry FSM.

### Intent
- **Normal** — штатный полный автоматический заряд, V1-compatible: bounded recovery и final Mix разрешены по детерминированным критериям.
- **Recovery** — тот же безопасный контур с явной восстановительной целью/диагностическим контекстом; evidence/safety не обходятся.
- **Conditioning** — сервисная цель внутри разрешённого chemistry envelope; generic EFB extension выше 16.5 V не существует.
- **Diagnostic** — наблюдение/проверка без автоматического создания Recovery/Mix.

`Auto Mix` — не intent, а direct-entry program mode.

## Production authority
- `AutoStrategyProductionChargeControllerV2` владеет AUTO Main/timeout/Mix strategy.
- `DiagnosticProductionChargeControllerV2` добавляет hypothesis-specific HV veto.
- `ProductionManualSessionManager` владеет Manual.
- `V2RuntimeSafetyGuard` + configured-value readback + verified OFF + edge lease — отдельная неотключаемая аппаратная граница.
- `DiagnosticActionJournal` хранит lifecycle диагностических действий, но не заменяет safety/chemistry authority.

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

Непроверяемая ошибка -> fail closed. Absolute working-voltage ceiling V2 = **17.5 V**; конкретный chemistry recipe может быть существенно ниже. Для EFB automatic/Recovery/Conditioning generic ceiling = **16.5 V**.

## AUTO start / PREP
```text
Vbat < 12.0 V  -> PREP, ~12 V + temp compensation, ~0.01C
Vbat >= 12.0 V -> MAIN сразу + PREP_SKIPPED audit event
```

Выбор делается до первого Output ON. Restore сохраняет persisted stage/target и не повторяет initial shortcut.

## AUTO Mix-only
`Auto Mix` стартует напрямую в `STAGE_MIX`:
- PREP/Main/intermediate Recovery не выполняются даже транзитно;
- `Vbat < 12.0 V` -> reject, не fallback в PREP;
- Ca/Ca/EFB -> standard Mix 16.5 V;
- AGM -> standard Mix 16.3 V;
- ~0.03C, max 12 A;
- normal ~120s blanking, CV `Imin -> ΔI`, CC `Vmax -> ΔV`, 3 spaced confirmations, sticky 2h hold;
- fallback Ca20/EFB24/AGM10;
- SAFE_WAIT -> Storage 13.8 V/1 A Output ON;
- strong `BLOCK_AUTOMATIC_HV` проверяется до включения;
- EFB >16.5 V не разрешается никаким generic `expert` flag.

## AUTO targets
Global stage-current ceiling: 12 A.

### Main
- ~0.1C, max 12 A;
- Ca/Ca 14.7 V;
- EFB 14.8 V;
- AGM 14.4 -> 14.6 -> 14.8 -> 15.0 V;
- temperature compensation внутри recipe envelope.

### Intermediate recovery / Desulfation
- 16.3 V base;
- ~0.02C;
- 2h;
- bounded intermediate attempt, не final Mix.

### Mix
- Ca/Ca 16.5 V;
- EFB 16.5 V;
- AGM 16.3 V;
- ~0.03C, max 12 A.

### EFB upper-envelope rule
Generic EFB chemistry policy has no automatic/Conditioning extension above 16.5 V. Passing `expert_high_voltage=True` must not enlarge the EFB envelope or set `expert_authorized`.

The global **17.5 V** ceiling remains available to first-class Manual/Custom operator authority under immutable safety. A future automatic EFB target >16.5 V would require a separate exact model-specific manufacturer-backed profile; chemistry label `EFB` alone can never grant it.

### Done / Storage
```text
SAFE_WAIT -> Done/Storage -> ~13.8 V / 1.0 A -> Output ON
```
Fault/hard-stop — отдельная OFF-семантика.

## Main evidence
Normal tail и stuck plateau — разные механизмы.

Tail:
- Ca/EFB: CV + I<~0.30A, 3h continuous hold/no new minimum;
- AGM: CV + I<~0.20A, 2h, staged Main.

Plateau:
- Ca/EFB ~40min flat CV plateau;
- AGM ~2h;
- плавное снижение тока = progress, не plateau.

Universal `>~1%C => HV veto` отклонён.

## Recovery budget
### Ca/Ca / EFB
```text
plateau -> recovery #1 -> Main
later plateau -> recovery #2 -> Main
later plateau -> recovery #3 -> Main
next confirmed plateau -> final Mix
```
Три попытки — budget всей session; progress count не обнуляет.

### AGM
```text
plateau -> recovery #1 -> Main
...
plateau -> recovery #4 -> Main
next plateau -> remain Main, НЕ forced Mix
```
После budget ждём normal low-current tail либо 72h conservative fallback.

## Main 72h fallback
- Ca/Ca/EFB Normal/Recovery/Conditioning: `Main 72h -> Mix`;
- AGM: `Main 72h -> Mix` только если CV и `I <= 0.20 A`, иначе `stop + diagnose`;
- Diagnostic: `stop + diagnose`, без auto-HV.

72h — strategy fallback, не generic hard-safety timeout.

## Mix
После target change ~120s blanking.
- CV: `Imin -> confirmed ΔI rise`, ориентир `max(0.03A, 30%*Imin)`;
- CC: `Vmax -> confirmed ΔV fall`, ориентир ~0.03V;
- 3 confirmations ~60s apart;
- confirmed event starts sticky 2h finish hold.

Fallback:
| Chemistry | Max Mix fallback |
|---|---:|
| Ca/Ca | 20 h |
| EFB | 24 h |
| AGM | 10 h |

## Diagnostic HV veto
Сначала strategy выбирает действие. Затем hypothesis engine может veto **новое** `ENTER_DESULFATION`/`ENTER_MIX` только при `BLOCK_AUTOMATIC_HV`. Один score/SG/U/I sample этого не создаёт. AGM voltage-step внутри Main не считается HV escalation. Auto Mix использует тот же veto как preflight.

## SAFE_WAIT
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
- recovery budget, AGM step, extrema, confirmed sticky delta preserved;
- stuck plateau and incomplete delta confirmations invalidated;
- durable restore required.

Manual: >=40C -> OFF/Cooling, <=35C -> safe re-enable same V/I, >=45C -> terminal stop. Active timer freezes; unfinished reach/delta continuity starts fresh.

## MANUAL
Manual — полноценный режим, не debug escape hatch и не legacy `Idle + Output ON`.

Operator owns working V/I and optional timer/V/I/reach/delta stop conditions. OVP/OCP всегда derived и не могут быть ослаблены.

Limits:
- `0 < V <= 17.5 V`;
- `0 < I <= 12 A`.

Pb chemistry rules не выполняются. Every start/reconfiguration проходит через transactional safe-enable; active reconfiguration делает verified OFF -> fresh enable.

### Optional physical-battery identity
Manual можно привязать к сохранённому `battery_id`, но **только** для longitudinal history/diagnostics:

```text
saved battery identity
        -> history label / diagnostic correlation
        X  chemistry does not choose Manual V/I
        X  Ah does not derive Manual current
        X  identity does not grant HV permission
```

Если запись АКБ удалена, сохранённый bound request нельзя молча перепривязать к другой АКБ.

### Restart / re-authorization
Persisted active Manual всегда восстанавливается как `INTERRUPTED`, Output не включается автоматически. UI показывает сохранённые V/I/OVP/OCP/stop conditions/battery identity и требует явного `Авторизовать заново`.

Fresh re-authorization:
```text
operator review
-> fresh telemetry/safety
-> fresh OVP/OCP + V/I programming
-> configured readback
-> Output enable/verification
-> new active-time clock
```

Старый active-time timer после process restart не продолжается. Operator может вместо reauthorize отменить сохранённый request; OFF подтверждается отдельно.

## AUTO user OFF condition
Persistent `Manual-OFF` во время AUTO — только parallel terminal kill-condition.

```text
AUTO chemistry FSM ---------------------> PREP/Main/Recovery/Mix/SAFE_WAIT/Storage
          |
          +---- armed user OFF condition
                         |
                         +---- not reached -> no influence on AUTO decisions
                         +---- reached     -> Output OFF + session STOP
```

Armed state не подавляет Recovery/Mix/72h/normal completion. После user terminal OFF нельзя автоматически включать Storage.

## Post-heavy-recovery rest
После тяжёлого recovery/corrective cycle V2 может рекомендовать **24–48h отдыха/наблюдения**, но это не lockout.

Useful checkpoints: ~1h / 6h / 12h / 24h / 48h. Полезно сохранять Vbat/OCV trend, T, SG, recovery response и `battery_isolated=yes/no`.

Elapsed rest time сам по себе никогда не запрещает Normal/Recovery/Conditioning/Manual/Auto Mix. HV veto допустим только из реальной safety/diagnostic evidence.

## Battery diagnostics / Bank Fault
V1 one-score `bank_fault` = evidence, not proof. V2 separates cell fault, self-discharge, sulfation, stratification, capacity loss, thermal abnormality and charger/path fault.

### SG
Raw per-cell SG is primary external evidence. Store six positional cells, raw SG, temperature, timestamp/context/source/notes. First complete spread >=0.030 = imbalance/stratification evidence, не short-cell proof и не automatic equalization veto.

Physical access is explicit per battery:

```text
SGAccess.UNKNOWN       -> SG не принимаем/не просим автоматически
SGAccess.SERVICEABLE   -> SG разрешён
SGAccess.INACCESSIBLE  -> SG не просим; отсутствие SG не fault evidence
```

- AGM: SG никогда не запрашивается.
- EFB/Ca/Flooded: chemistry сама по себе не означает доступ к электролиту; нужен explicit `SERVICEABLE` именно для этой физической АКБ.

Hydrometer/correction metadata belongs to each measurement:

```text
hydrometer=unknown -> raw only
hydrometer=raw     -> raw primary; optional explicit manufacturer profile
hydrometer=tc      -> instrument already compensated; NEVER software-correct again
```

Named software profiles currently supported only by explicit operator selection:
- `trojan80`: Trojan convention around 80 F, +/-0.004 per 10 F;
- `rolls25`: Rolls flooded-manual convention around 25 C, +/-0.003 per 5 C.

Manufacturer/model text never auto-selects a profile. Named profile requires `hydrometer=raw` + electrolyte `t=...`. Detailed source/policy: `SG_POLICY_V2.md`.

Proactive SG prompt is deliberately sparse:
- no routine prompt on every charge;
- `DIAGNOSTIC_VERIFY` or stronger only for SG-relevant hypotheses (`cell_fault`, `stratification`, `sulfation`) and only with confirmed `SERVICEABLE` access;
- `POST_CORRECTIVE_RETEST` when earlier SG actually showed imbalance and a manufacturer-appropriate corrective cycle was performed;
- unsafe/inaccessible/unavailable measurement -> no prompt and no confidence penalty.

Q013 still owns calibration of when the hypothesis engine reaches VERIFY/PROBABLE/HIGH; D053 owns SG eligibility once it does.

### Bank-Fault calibration
Current score weights and `15/35/60/80` level boundaries are not tuned from synthetic examples. Labeled real cases are replayed deterministically through `battery_fault_calibration.py` / `tools/evaluate_battery_fault.py`.

The report keeps two safety-significant error classes separate:
- unexpected `BLOCK_AUTOMATIC_HV`;
- missed labeled `BLOCK_AUTOMATIC_HV`.

Hypothesis-level mismatches are reported separately and never trigger automatic threshold tuning. Exact labeling workflow: `BANK_FAULT_CALIBRATION.md`.

### Dynamic loop
RD displayed `V/I` is not battery Ri. Controlled current reduction may produce `dynamic_loop = ΔV_BAT/ΔI`, but two-wire black+green path includes battery+cables+contacts+internal path+polarization. Compare longitudinally only with explicit unchanged connection identity.

### Diagnostic persistence / restart
Durable **evidence** и diagnostic **action state** разделены.

Evidence such as completed SG/probe/recovery history may survive restart. Derived diagnostic authority (`ALLOW/VERIFY/BLOCK_AUTOMATIC_HV`) is recomputed; it is not trusted merely because an old process once calculated it.

Restart matrix:
| State/action | Restart behavior |
|---|---|
| completed SG/dynamic-loop/recovery evidence | keep |
| in-flight controlled probe | `ABORTED_RESTART`, never resume mid-step; Output OFF defense-in-depth |
| pending operator confirmation | expire; ask again |
| pending fault verification | expire; require fresh evidence/operator action |
| expert-HV authorization | revoke; never survive restart |
| rest-observation window | may survive until expiry because it has no actuator authority |
| derived HV-block assessment | recompute from durable/fresh evidence |

No crash recovery may guess and restore a mid-probe current setpoint.

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
- Post-heavy-recovery rest — recommendation/diagnostic window, не time-based lockout.
- Manual battery identity — history metadata, не chemistry authority.
- Diagnostic action after restart never auto-resumes authority-bearing work.
- SG access is physical-battery metadata; chemistry alone never grants electrolyte access.
- Never double-correct `hydrometer=tc`; manufacturer correction is explicit, never inferred.
- EFB automatic/Recovery/Conditioning generic ceiling is 16.5 V; global 17.5 V is Manual/Custom outer authority, not EFB chemistry permission.
- Если вопрос находится в `V2_OPEN_QUESTIONS.md`, не додумывай решение по памяти.
