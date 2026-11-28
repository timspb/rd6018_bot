# R20-A07 — zHit, repeatability and grouped residual capacity baseline
2026-11-28. PARTIAL; offline scientific research only.
Source: Kwiecien et al. 2018 DOI 10.3390/app8060873, https://www.mdpi.com/2076-3417/8/6/873 , §§2.2,3,5 and original archived supplement from R20-A06. Same four physical cells, not new independent cohort.
## Implementation and limitations
tools/r20_eis_zhit_audit.py transcribes author zhit.m one-gamma logarithmic integral, first derivative, mean offset and exponential reconstruction. Does not execute archived MATLAB code. Synthetic series RC median relative reconstruction error 0.0003364 (0.03364%); sanity check only. Uses direct whole-cell channels, removes zero/nonfinite values and adjacent duplicate frequencies (last retained), requires strictly descending frequency. Not exact author electrode-subtraction mask; native raw units retained because _Ohm field vs mOhm plot labels unresolved. Author plot absolute threshold 0.15 in native numerical units, not 15% and not new calibrated threshold. Endpoints excluded by formula. Independent scipy decode still blocked by missing numpy/scipy in local venv; no claim of validated exact reproduction.
2104 spectra processed; 6278 adjacent duplicates removed; 78962 interior points, 56721 within threshold (71.83%). 38 Digatron files, 661329 rows, no decreasing timestamps. 130 selected -3I20 spectra and 129 -1I20 spectra (mini-cycles 1/2, 80per/aftCHA/aftCyc). Same selection across biases not guaranteed because one missing file; descriptive only.
| bias | target Hz | accepted/total | repeat pairs accepted both at same exact frequency | median abs percent change | max abs percent change |
|---|---|---|---:|---:|---:|
| -3I20 | 1000 | 121/130 | 58 | 0.205 | 1.389 |
| -3I20 | 10 | 130/130 | 65 | 1.324 | 4.745 |
| -3I20 | 0.1 | 49/130 | 17 | 1.826 | 2.344 |
| -1I20 | 1000 | 126/129 | 61 | 0.745 | 2.244 |
| -1I20 | 10 | 123/129 | 60 | 1.237 | 6.714 |
| -1I20 | 0.1 | 95/129 | 42 | 7.616 | 14.133 |
Selection at nearest frequency within factor 1.25; repeat comparisons exact equality, mini-cycles perturb charge state and are not independent instrument repeatability. Both acceptance and repeat consistency needed. Low-bias result at 0.1Hz agrees qualitatively with source recommendation, but repeatability worse and retained pair populations differ. No causal conclusion or universal threshold.
After stage filtering, -3I20 first mini-cycle median aftCHA/aftCyc at ~1kHz: TC1 hard 1.0853 (6 pairs), TC2 hard 0.9782 (9). At ~10Hz 1.1777 (8), 1.0576 (10). No retained pairs at 0.1Hz. At -1I20: 1kHz 1.0837 (7),0.9869 (10); 10Hz 1.2098 (7),1.0795 (10); 0.1Hz 1.3612 (3),1.1699 (5). Actual SOC not matched, no claim of desulfation or treatment causality.

## Capacity recovery from logged traces
tools/r20_eis_capacity_candidates.py locates contiguous -2A ±0.05A segments >600s ending at <=1.83V and trapezoid integrates measured current. 39 candidate segments across 35 checkup folders; 4 extra baseline repetitions, not independent labels. Source §2.2 confirms nominal 10Ah cells, I20=0.5A, residual capacity after cycling at -4I20 to 1.8V. This is C_res after cycling with unspecified SOC, NOT fully charged C20/SOH. Source explicitly recognizes SOC drift and possible assembly defect in TC1 soft. Endpoint integration omits sample edges, so small differences vs paper expected. TC1 hard final 0.922Ah vs published 0.94; TC2 hard 2.8227 vs 2.84; TC1 soft 0.8192 vs 0.82. Do not infer calibrated accuracy.
| FCE | TC1 hard | TC2 hard | TC1 soft | TC2 soft |
|---:|---:|---:|---:|---:|
| 15 | 10.4030 | 9.0221 | 9.3980 | 10.0787 |
| 45 | 7.8566 | 7.3959 | 5.8116 | 8.3273 |
| 90 | 4.4269 | 5.1233 | 0.8192 | 4.9931 |
| last | 0.9220 (135) | 2.8227 (150) | 0.8192 (90) | 4.9931 (90) |
TC2 soft still ongoing in paper; no endpoint equivalence or claim soft worse.

## Exploratory leave-one-physical-cell-out
tools/r20_eis_capacity_join.py uses 31 nonbaseline unique C_res candidates (cutoff 1.77–1.83V), joins exact cell/checkup aftCyc -1I20 mini-cycle 1, retains common complete-case set with accepted ~1kHz and ~10Hz. 26 rows, 4 cells. Three separate untuned OLS regressions, C_res on FCE or raw magnitude at one frequency; train on 3 cells, test entire fourth; no same-cell row leakage. Not a prospective diagnostic study; stage join by folder and source protocol, no timestamp alignment between instruments. Test fold MAE Ah:
| held out | n | FCE | 1kHz | 10Hz |
|---|---:|---:|---:|---:|
| TC1 hard | 7 | 0.834 | 1.275 | 1.279 |
| TC1 soft | 3 | 0.898 | 2.537 | 3.940 |
| TC2 hard | 10 | 0.932 | 0.415 | 1.345 |
| TC2 soft | 6 | 0.650 | 0.783 | 1.233 |
FCE wins 3/4 folds versus 1kHz and 4/4 versus 10Hz. TC1 soft known suspected assembly defect and only three complete cases; no removal post hoc. FCE baseline not universal in unknown history, not an operational alternative to EIS. This dataset does not establish benefit of single-frequency impedance over cycle count for cross-cell C_res prediction under this specific protocol and model. No population confidence interval, chemical classification, C20 prediction or automotive transfer.
Candidate C124: zHit acceptance depends on bias/frequency, does not establish repeatability.
C125: filtered 1kHz post/pre direction differs between hard cells, SOC uncontrolled.
C126: trace integration reproduces C_res endpoints approximately; residual capacity not fully charged C20.
C127: untuned held-out cell baseline FCE outperforms single-frequency models in most/all folds; not independent validation.
H75: multi-frequency plus known preparation and history improves cross-cell C_res estimates beyond single features and cycle baseline; requires separate independent data.
Next: independent MAT decoder, exact author mask/units, paired bias comparison, edge integration and timestamp check; compare OCV/FCE baseline and multiband without posthoc selection; acquire independent larger datasets. R20-A06/A07 ledger candidates not yet committed; publication pending. No equipment changes.
