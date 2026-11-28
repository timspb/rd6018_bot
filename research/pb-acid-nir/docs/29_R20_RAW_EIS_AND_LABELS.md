# R20-A06 — Raw EIS acquisition and preliminary reanalysis
2026-11-28. PARTIAL. Research only; no physical tests or production changes.

## Original data
Kwiecien et al. 2018, DOI 10.3390/app8060873. Article https://www.mdpi.com/2076-3417/8/6/873 and original supplementary archive https://mdpi-res.com/d_attachment/applsci/applsci-08-00873/article_deploy/applsci-08-00873-s001.zip .
Local sources/R20/Kwiecien_2018_supplement_alt.zip, 14,804,227 bytes, SHA256 96d49538c06b931c77cde65bbfedf7aa5584c049dcd30e336938c1c18197f60a.
2335 ZIP entries, 2259 files, 2142 MAT files including 2104 spectra. Four physical cells, 35 checkups (hard TC1 10, hard TC2 11, soft TC1/TC2 7 each). Repeated spectra are not independent specimens. Author Documentation.pdf pages 5–9 examined. File names encode current relative to I20=0.5A, mini-cycle 1/2, nominal SOC or preparation stage aftCHA/aftCyc (actual SOC unspecified). Raw field names _Ohm versus author plot axes mOhm need reconciliation.

## Executed raw audit
tools/r20_eis_raw_audit.py parsed all 2104 EIS MAT files with zero errors using a restricted standard-library MAT v5 decoder. Independent scipy comparison pending; base Windows and WSL lack scipy. Selected 65 unique spectra at -3I20 mini-cycle 1, 80per/aftCHA/aftCyc, across 35 checkups. Nearest finite nonzero magnitude to each target frequency within factor 1.25. No missing selected targets. No zHit, stationarity validation or repeat aggregation yet. Ratios only, no absolute unit conversion.
Nominal 80% SOC |Z|90FCE/|Z|baseline at approximately 1066.667,10.676,0.107Hz:
| Cell | ~1kHz | ~10Hz | ~0.1Hz |
|---|---:|---:|---:|
| TC1 soft | 1.4291 | 1.4886 | 1.3608 |
| TC2 soft | 1.2923 | 1.3030 | 1.2368 |
Hard cells lack matching files under this exact selection, not imputed.
Median raw |Z|aftCHA/|Z|aftCyc ratios:
| Cell | pairs | ~1kHz | ~10Hz | ~0.1Hz |
|---|---:|---:|---:|---:|
| TC1 hard | 8 | 1.0789 | 1.1777 | 1.1236 |
| TC2 hard | 10 | 0.9753 | 1.0576 | 1.0379 |
Counts decreasing: TC1 1/1/1 of 8; TC2 8/1/3 of 10. No soft matched pairs under selection. No population inference. SOC confounding, raw point validity pending. No universal postcharge impedance decrease in these raw observations; no chemical conclusion.

## Extended primary study
Kwiecien 2019 dissertation DOI 10.18154/RWTH-2019-09480, https://publications.rwth-aachen.de/record/768701/files/768701.pdf. Original PDF text ch5/6, Tables5.1–5.4; web screenshots rejected due to size, local download HTML instead of PDF. Same research lineage, not independent replication. Seven cycling and three corrosion cells. TC173-3 ~30% residual nominal capacity, bottom NAM SO4 8.40% vs TC173-1 23.36% and TC173-7 25.49%. Positive electrode impedance change larger than negative; authors suspect shedding but request porosity analysis. TC173-2 bottom NAM SO4 7.68%, nearly unchanged spectra, separator holes and shorts. Two other corrosion runs ongoing at thesis completion; significant corrosion endpoint missing, not validated corrosion discriminator. SO4 assay is not direct pure PbSO4 mass; similar assay with different impedance is consistent with distribution or other mechanisms, not proof. TC181-2 §5.3.1 explicit endpoints 3.7→7.6Ah (+3.9Ah); later §5.3.1.1 wording +7.6Ah conflicts; original figure not visually verified. No durability or matched control. No hardware protocol extrapolation.

## Candidate conclusions for ledger review
C118: 2104 spectra, four cells and 35 checkups; independent sample size distinction.
C119: raw soft-cell 90FCE ratios heterogeneous; zHit pending.
C120: paired raw stage ratios heterogeneous, SOC unspecified; no universal decrease.
C121: severe capacity loss with relatively low NAM SO4 and larger PAM impedance; shedding suspected not confirmed.
C122: incomplete corrosion endpoints prevent validation of corrosion discriminator.
C123: dissertation TC181-2 endpoint wording discrepancy.
H73: multiband and preparation-state features may improve single-frequency screening under validity and grouped controls.
H74: sulfate distribution and active mass integrity may account for different spectra with similar chemical assay.

## Next
Verify decoder independently, reconcile units, validate zHit, match actual frequencies, quantify mini-cycle repeatability, integrate Digatron trace capacity with correct stage and cutoff, compare baseline and grouped physical-cell holdout. Four cells only, exploratory. Independent labeled corrosion/dryout data remain open. BBOXX field cohort candidate for operational SOH only. No hardware changes. Registry candidate IDs not counted as committed until validation and publication.
