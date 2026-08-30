# V2 Specific-Gravity Policy

Status: **ACCEPTED / IMPLEMENTED FOUNDATION + UI**

This document defines when V2 may ask for per-cell electrolyte specific gravity (SG), how physical access is represented, and when a temperature-corrected view may be calculated.

## 1. Raw SG is the primary evidence

Every measurement keeps the six positional cell values exactly as reported, plus measurement timestamp, electrolyte temperature when supplied, context/source/notes and the explicit hydrometer/correction metadata.

V2 never rewrites the stored raw values. Relative evidence such as same-sample cell spread/outliers is calculated from the raw same-context readings. A first complete spread >=0.030 remains imbalance/stratification evidence, not proof of a shorted cell and not an automatic HV veto.

## 2. Electrolyte access belongs to the physical battery

`SGAccess` is stored independently from chemistry:

- `UNKNOWN` — V2 does not know whether the cells can be sampled;
- `SERVICEABLE` — operator has explicitly confirmed safe physical access to the electrolyte/cells;
- `INACCESSIBLE` — cells cannot be sampled without defeating the battery construction/service boundary.

Rules:

- AGM: never request per-cell SG.
- EFB: liquid-electrolyte chemistry does **not** imply serviceable caps. SG requires explicit `SERVICEABLE` for that physical battery.
- Ca/Ca/Flooded: chemistry also does not automatically grant access; sealed/maintenance-free constructions exist. `UNKNOWN` must be resolved before accepting/proactively requesting SG.
- `INACCESSIBLE` or unavailable SG never raises a fault score.

Why this is explicit: VARTA describes EFB as an enhanced flooded/liquid-electrolyte design while also describing current EFB products as maintenance-free/closed. Therefore chemistry is not a reliable proxy for operator access.

Reference:
- https://www.varta-automotive.com/de-de/knowledge/technology/efb

## 3. Hydrometer mode belongs to the measurement

`HydrometerMode`:

- `UNKNOWN`
- `RAW` — ordinary non-temperature-compensated reading
- `TEMPERATURE_COMPENSATED` — instrument already compensates the reported reading

A temperature-compensated hydrometer must **never** receive a second software temperature correction.

## 4. Correction profiles are explicit, never inferred

`SGCorrectionProfile`:

- `RAW_ONLY` — no V2 numeric correction;
- `TROJAN_80F` — explicit Trojan maintenance convention;
- `ROLLS_25C` — explicit Rolls flooded-battery manual convention.

V2 never selects one of these from the `manufacturer` or `model` string. The operator/profile workflow must explicitly choose it.

A named manufacturer profile requires:

1. `hydrometer=raw`;
2. electrolyte temperature `t=...`;
3. explicit profile selection.

If any of these are absent, V2 keeps raw SG only and does not manufacture a corrected value.

### Trojan 80 F convention

Trojan's Battery Maintenance material specifies correction to 80 F (~26.7 C): add/subtract 0.004 SG for each 10 F (~5.56 C) above/below 80 F.

V2 profile approximation:

```text
SG_corr = SG_raw + 0.004 * (T_C - 26.6667) / 5.5556
```

References:
- https://www.trojanbattery.com/resources/battery-maintenance
- https://www.trojanbattery.com/resources/faqs

Trojan also states that equalization is for flooded batteries and recommends it when low or wide-ranging SG (>0.030) remains after full charge, followed by retesting. This supports the V2 rule that first SG imbalance is evidence for verification/corrective action, not immediate failed-cell proof.

### Rolls 25 C convention

The current Rolls flooded-battery manual expresses SG at 25 C (77 F) and gives an adjustment of 0.003 for each 5 C (10 F) increase/decrease.

V2 profile approximation:

```text
SG_corr = SG_raw + 0.003 * (T_C - 25.0) / 5.0
```

References:
- https://rollsbattery.com/wp-content/uploads/2018/01/Rolls_Battery_Manual.pdf
- https://support.rollsbattery.com/en/support/solutions/articles/208145-specific-gravity-temperature-correction
- https://support.rollsbattery.com/en/support/solutions/articles/4347-measuring-specific-gravity

Rolls support material contains multiple ways of expressing the correction (table/rule/equation). This is another reason V2 never silently guesses a convention. The named profile is an explicit software convention tied to the documented manual rule, while raw readings remain preserved.

## 5. Proactive prompt policy

V2 does **not** ask for SG on every charge.

A proactive prompt is allowed only when all of the following are true:

- chemistry is not AGM;
- the exact physical battery has `SGAccess=SERVICEABLE`;
- measurement is safe at the current operator/charge context;
- SG can resolve a concrete diagnostic ambiguity or close a prior corrective loop.

Accepted prompt points:

### `DIAGNOSTIC_VERIFY`

Prompt at diagnostic level `VERIFY` or stronger when the unresolved hypothesis is one where cell SG is materially useful:

- `cell_fault`;
- `stratification`;
- `sulfation` / poor acceptance.

Do not prompt for unrelated hypotheses such as charger/path-only evidence.

### `POST_CORRECTIVE_RETEST`

Prompt after a manufacturer-appropriate corrective cycle when an earlier SG measurement actually showed cell imbalance and a retest is needed to determine whether it improved/persisted.

### `ROUTINE`

No proactive prompt. Manual SG entry remains available, but V2 does not nag on every ordinary charge.

The automatic decision to enter a `DIAGNOSTIC_VERIFY` state and the confidence thresholds that produce it remain part of Q013 calibration. Q012 only defines SG eligibility and what V2 may ask once that state exists.

## 6. Interpretation boundary

SG is external evidence, not actuator authority by itself.

```text
first wide SG spread
    -> imbalance / stratification evidence
    -> VERIFY
    -> manufacturer-appropriate corrective cycle may be useful
    -> retest

persistent same-cell abnormality after corrective cycle
    + independent U/T/relaxation/recovery evidence
    -> stronger cell-fault hypothesis
```

A single low cell does not directly produce `HARD_STOP` or `BLOCK_AUTOMATIC_HV`. Those decisions still require the multi-signal authority boundary from D028/Q004.

## 7. Telegram input

Examples:

```text
1.275 1.272 1.270 1.180 1.274 1.271; t=25; context=post_charge; hydrometer=raw
```

Explicit Trojan convention:

```text
...; t=25; hydrometer=raw; profile=trojan80
```

Explicit Rolls convention:

```text
...; t=25; hydrometer=raw; profile=rolls25
```

Temperature-compensated instrument:

```text
...; hydrometer=tc
```

No profile may be combined with `hydrometer=tc`; that would double-correct the reading.
