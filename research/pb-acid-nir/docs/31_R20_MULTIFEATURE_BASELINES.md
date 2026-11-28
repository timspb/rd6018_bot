# R20-A08 — Incremental value of multiple impedance features
2026-11-28. PARTIAL; original Kwiecien 2018 supplement, same four cells as A06/A07.
Executed tools/r20_eis_multifeature.py. Fixed exploratory models, training-fold standardization, OLS or ridge lambda=1 on standardized coefficients (sum squared error, unpenalized intercept). Leave one physical cell out; common 26 residual after-cycling capacity observations, not fully charged C20. No hyperparameter search. A07 parser/units/zHit mask and temporal linkage limitations persist. OCV not joined; do not claim OCV comparison.
| Model | TC1 hard | TC1 soft | TC2 hard | TC2 soft | Macro MAE Ah | Pooled MAE Ah |
|---|---:|---:|---:|---:|---:|---:|
| FCE OLS | .8338 | .8984 | .9315 | .6498 | .8284 | .8364 |
| 1kHz OLS | 1.2750 | 2.5374 | .4145 | .7830 | 1.2525 | .9762 |
| 10Hz OLS | 1.2789 | 3.9398 | 1.3446 | 1.2325 | 1.9489 | 1.6005 |
| FCE ridge | .9050 | .8175 | .7619 | .7130 | .7994 | .7956 |
| 2-band ridge | 1.2704 | 3.0883 | .4445 | .8720 | 1.4188 | 1.0706 |
| FCE+2-band ridge | .8331 | 1.4027 | .7513 | .5806 | .8919 | .8091 |
| FCE+1kHz+log(10Hz/1kHz) ridge | .8734 | 1.0278 | .8316 | .5781 | .8277 | .8070 |
Macro means equal weight per physical cell. Pooled weights each checkup equally. Neither multifeature variant beats FCE ridge on the primary common set. No causal or population inference; 4 cells, shared research cohort, exploratory models.
## Sensitivity to inclusion of 0.1Hz
24 complete cases: 6,2,10,6 per cell in table order. Same rows for all models.
| Model | Macro MAE Ah | Pooled MAE Ah |
|---|---:|---:|
| FCE OLS | .9205 | .8664 |
| FCE ridge | .8835 | .8098 |
| FCE+2-band ridge | .8972 | .7733 |
| FCE+3-band ridge | .8939 | .7765 |
Pooled metric improves with 2 bands in this subset but equal-cell macro metric worsens; 0.1Hz does not improve pooled MAE over 2-band and only changes macro by .0033Ah. Selection and metric dependence preclude a universal advantage. TC1 soft has only two retained rows in this subset. Known FCE is an experimental-history baseline, not a substitute for measuring an unknown used battery.
## Conclusions
C128 — On the primary common set (26 observations, 4 cells), fixed FCE ridge has lower macro and pooled MAE than tested multi-band models with or without FCE. This is negative evidence for incremental feature value in this cohort, not proof that EIS is ineffective.
C129 — On the 24-row three-frequency complete-case subset, the conclusion depends on macro vs pooled MAE; adding 0.1Hz has no robust incremental benefit. Report both metrics, common denominators, and physical-cell folds.
H76 — Independently measured pre-discharge resting voltage and charge-history features may improve residual-capacity estimates relative to the FCE baseline; requires verified timestamp ordering and independent cells.
Next: verify pre-label voltage/rest and temperature features, then independent MAT decoding and larger external field cohort. No OCV label inferred from arbitrary last voltage. No hardware/production changes.
