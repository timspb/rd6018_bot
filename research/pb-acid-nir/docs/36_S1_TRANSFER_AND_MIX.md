# S1 — переносимость DCA, газ и внутрипоровый транспорт
2026-11-29. Research-only continuation of reports 34–35; no operational charge profile.

## S09 Bauknecht et al., Energy Technology 2022, DOI 10.1002/ente.202101053
Original PDF https://d-nb.info/125261697X/34 ; machine text methods, Fig. 5 and Table A1 checked; screenshot cache miss. Industrial 70 Ah EFBs, extracted complete 8P8N/8P9N and reduced 3P2N/2P1N cells; acid adjusted to estimated state, spacers do not remove acid/NAM/PAM geometry differences. EN 50342-6 DCA in A/Ah:
| Type | Battery | Full cell | 3P2N | 2P1N |
|---|---:|---:|---:|---:|
| 1-C | .298 | .190 | .330 | .412 |
| 1+C | .401 | .226 | .398 | .474 |
| 2+C | .543 | .388 | .632 | .710 |
| 3+C | .525 | .437 | .770 | .800 |
Ratios and rank checked with s1_transfer_math.py. Battery 2+C > 3+C, reduced cells reverse order; not a universal material rank. Some high DCA results limited by test current; type 2 middle/small failures excluded from run-in correlation. Sample independence/replicates not established from extracted text; no significance claims. Short DCA is not lifetime or acceptance throughout all SOC, nor a high-voltage charge criterion. EFB+C is authors' enhanced DCA classification, not proof carbon is sole causal variable. Supports R14-Q comparative primary numbers, not R14-K.

## S10 Flow cell, J. Electrochem. Soc. 170 050523 (2023), DOI 10.1149/1945-7111/acd351
Full machine-readable article via https://www.researchgate.net/publication/370627391_Flow_Cell_for_Simultaneous_In_Situ_Analysis_of_Local_Electrolyte_Distribution_and_Porous_Morphology_within_the_Negative_Electrode_in_a_Lead-Acid_Battery . Fig6–9 text and method. Special negative electrode, imposed constant hydraulic pressure, gravimetric flow sampled every 2 min. Normalized flow fell 1→0.3 within 6 min during gassing, then recovered to ~1 over 80 min after a later charge; authors attribute to retained hydrogen bubbles. During discharge flow declined with sulfate deposition; no independent pore imaging confirming each obstruction. Forced flow differs from bulk convection in commercial battery; no universal pause duration, no quantified MIX efficacy, no transfer of test apparatus to consumer batteries. The result distinguishes bulk density homogenization from pore-level transport: simultaneous bulk mixing and pore restriction are physically compatible. R09-Q still open: no matched SG(z), water-loss and reference-capacity experiment for proposed MIX.

## S11 Takamatsu et al., Chem Commun 2020 DOI 10.1039/D0CC03592K
Publisher abstract plus original supplementary information https://www.rsc.org/suppdata/d0/cc/d0cc03592k/d0cc03592k1.pdf ; screenshot cache miss. Model glass cell, assumed 130 mAh from geometry, independently selected nominal test capacity 100 mAh; 15 s phase image cadence, 12.5 µm/pixel. Method converts phase signal to electrolyte density. Main article quantitative trajectories not retrieved; do not confuse estimated capacity with measured reference C20, or spatial image resolution with density uncertainty. Relevant candidate for independent bulk stratification measurements, not validation of MIX.

## Critical measurement matrix (S1)
| Claim being tested | Necessary independent target | Confounder / negative control | Evidence status |
|---|---|---|---|
| MAIN complete | reference discharge after standardized rest and model-specific charge; measured Q/T and true CV | matched ordinary charge; separate current limit and external load; false positive if low current but residual capacity deficit | E2 limited, no universal tail |
| MIX homogenizes | vertical density profile before/after, temperature corrected, calibrated sampling/measurement error | same SOC and temperature; matched ordinary charge and elapsed rest; separate water loss, average density, local transport | E2 Kwiecien model, E3 Mamadou incomplete; target commercial evidence open |
| Desulfation restores | independently measured functional reference and chemical/morphological label, capacity retention | ordinary charge, identical preparation, elapsed rest; reject causal attribution to treatment when change within uncertainty | E2 limited, R19 retention open |
| DCA predicts MAIN | independent reference after actual CV and same history | prior charge/discharge, plate geometry, electrolyte reserve; run-in and fresh tests separate | NOT_ESTABLISHED, S09 rank reversal |
| Bubbling proves mixing | SG(z) independently of gas detection, water/thermal monitoring | pore blockage and gassing before full charge; separate VRLA oxygen cycle | NOT_ESTABLISHED; no gas-onset universal criterion |
D09: TG104293 cited table not identified by phrase search including Pavlov and open circuit; remains unresolved provenance. TG105607 pauses and TG105526 density observations are compatible with transport effects but not independently validated. S10 flow recovery during rest does not reproduce either forum case; no numerical pause recommendation. No new Telegram raw access.

C145 — EFB DCA scales with geometry and acid reserve; Table A1 shows comparative rank reversal between battery and reduced cells. Short DCA not sufficient for universal transfer.
C146 — In one forced-flow negative-electrode study, normalized electrolyte flow fell 70% at gassing within 6 min and recovered during later rest. Bulk mixing and pore transport differ; no universal pause or gas criterion.
H81 — Joint independent vertical SG and pore-transport measurements may distinguish apparent bulk mixing from actual improvement of charge acceptance; test matched SOC/T/history and reference capacity, without inducing hazardous conditions.
