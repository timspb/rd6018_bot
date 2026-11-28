# R20-A09 — Rest voltage, relaxation, temperature and prior throughput
2026-11-28. PARTIAL. Same original Kwiecien 2018 dataset, DOI 10.3390/app8060873; no new physical specimens or equipment actions.
## Feature construction and chronology
tools/r20_rest_history_audit.py executed twice, final run includes common EIS subset. Uses A06–A08 decoder, residual discharge selection and fixed grouped ridge solver. 31 nonbaseline residual -2A discharge candidates with endpoint 1.77–1.83V; all 31 have logged zero-current rest (abs I <= .005A) 14400.00–14400.03s prior to full discharge. Last zero-current sample to full load gap 0.01–58.08s, includes ramp/transitions; features strictly from preceding zero-current plateau. No loaded voltage or discharge outcome used as feature. Label-selected completed discharges are retrospective and could bias coverage. OCV is measured quasi-rest voltage, not established thermodynamic equilibrium or full SOC.
Urest median of 14100–14410s from rest start; relaxation features median U at 600–900s and 3600–3900s minus Urest; temperature median same final window; prior positive/negative trapezoid-integrated Ah from beginning of current record up to rest boundary (not lifetime throughput, not true accepted charge). Four cells, temperature ~23.7–26.4C, strongly confounded with physical cell and protocol. Prior file charge/discharge throughput narrowly varying around 6.9Ah each, not independent variation of history. No causal inference about temperature or charging effects. Timestamp order verified within each file; EIS join still via cell/checkup/stage, cross-instrument alignment pending.
## Direct counterexample
TC1 hard 15 FCE: Urest 2.165V, residual Q 10.402995Ah, early/late delta 28mV, mid/late 13mV, T25.3C. At 135 FCE: Urest 2.165V, residual Q .922031Ah, deltas 25/11mV, T25.3C. Same measured Urest at logged resolution, residual Q differs ~11.28-fold. TC1 soft 15→90 FCE Urest 2.178→2.182V, Q9.39801→.819155Ah. Not C20 or population rule.
## All 31 observations, four held-out physical cells
Fixed OLS or ridge lambda=1, training-fold standardization; equal-cell macro MAE and pooled measurement MAE Ah. Not independent validation; earlier A08 results use 26-row subset, do not directly compare different denominators.
| Model | Macro | Pooled |
|---|---:|---:|
| FCE OLS | 1.4025 | 1.3395 |
| FCE ridge | 1.3901 | 1.3213 |
| Urest OLS | 2.8890 | 2.7257 |
| Urest+relax ridge | 3.3786 | 3.1257 |
| FCE+Urest ridge | 1.5140 | 1.4221 |
| FCE+Urest+relax ridge | 1.8351 | 1.7173 |
| FCE+Urest+relax+T ridge | 2.2480 | 2.2288 |
| FCE+prior Ah ridge | 1.4851 | 1.4108 |
| FCE+all prelabel ridge | 2.3405 | 2.3188 |
None beats FCE ridge on this complete trace set. No general claim that relaxation is useless.
## Common 26 EIS + rest observations, exploratory secondary comparison
| Model | TC1 hard | TC1 soft | TC2 hard | TC2 soft | Macro | Pooled |
|---|---:|---:|---:|---:|---:|---:|
| FCE ridge | .9050 | .8175 | .7619 | .7130 | .7994 | .7956 |
| Urest OLS | 1.9960 | 2.4898 | 1.7388 | 1.9160 | 2.0352 | 1.9356 |
| rest only ridge | 1.9705 | 2.5167 | 1.7442 | 2.1452 | 2.0941 | 1.9868 |
| FCE+rest ridge | .9945 | 1.2533 | .8180 | 1.2356 | 1.0754 | 1.0121 |
| FCE+two-band ridge | .8331 | 1.4027 | .7513 | .5806 | .8919 | .8091 |
| FCE+two-band+rest ridge | .6277 | 1.3134 | .6272 | .4068 | .7438 | .6557 |
Joint model improves equal-cell MAE ~7% vs FCE ridge and pooled MAE ~18%, wins 3/4 held-out folds, loses TC1 soft; this is exploratory, not pre-registered independent validation. Common-case exclusions 5/31 (3 of 6 TC1 soft, 2 of 9 TC1 hard); FCE baseline itself much better on retained subset. Do not infer benefit in excluded cases. Many models explored on same four cells, no credible population confidence or significance. EIS validity/mask/units and independent MAT decoder open. No physical diagnosis or charging parameters.
C130 — Four-hour quasi-rest voltage can be identical while subsequent residual capacity differs ~11-fold within one cell; not fully charged C20.
C131 — On 31 residual-capacity records, tested rest/relaxation/T/prior-Ah models do not beat FCE ridge; history and temperature narrowly varying/confounded.
C132 — On selected 26 common cases, joint EIS+rest+FCE improves macro and pooled MAE, but loses one physical-cell fold; exploratory selection-dependent signal, not validated diagnosis.
H77 — Complementarity of rest relaxation and multiband EIS can improve out-of-cell estimates when cycle history is known; predefine model, handle invalid spectra, test independent cohort and compare coverage-aware baselines.
Next: freeze exploratory models, inspect excluded cases and coverage-aware fallback without tuning; seek independent larger raw field datasets with discharge endpoints and charge/rest history. Do not repeat fitting same four cells as if external evidence. No equipment changes.
