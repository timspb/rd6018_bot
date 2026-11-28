# S5 D09 — extended longitudinal cycling, rest and measurement confounding
2026-11-29. Report52. Existing read-only MCP v0.2.0; only UklonGroup search/get/attachment, no writes to Telegram. Three queries 91/79/100 hits, 255 distinct message IDs across extension files (overlap with report51, not 255 additional messages). Raw JSONL and attachments local only. Three specimens/threads selected, not population samples.
## TG09 extension: Akom Standard
45556: specimen nominal 60Ah/540A EN, dated 2025-01-03, purchased 2025-05-27. 45592 first discharge after initial top-up 62.281Ah (author Q25 63.401). Early cycles missing in report51 now located:
| cycle | message | raw Ah | Q25 Ah |
|---|---|---:|---:|
|1|45592|62.281|63.401|
|2|45693|51.047|51.763|
|3|45761|54.317|—|
|4|45848|52.201|52.202|
|5|45925|48.287|48.677|
Cycle3 instrument reboot, retain with quality flag. Cycle2 previous charge 56.828Ah after 62.281Ah discharge (45639), so initial SOC not matched. Cycle25 42.412Ah (61695), relative to cycle1 −31.90%; 70.69% of nominal, not certified C20 or EOL. Public author spreadsheet link in 45556 not opened or validated; cutoff and temperature correction still unverified.
## TG14: Akom EFB thread14601
Separate specimens in search results (12815 and 42094) excluded from this series. Data from same thread only:
| cycle | message | raw Ah |
|---|---|---:|
|5|15453|36.758|
|6|15505|29.809|
|7 inferred by sequence|17178|26.026|
|8|17921|20.011|
|9|18832|15.60582|
|10|19670|12.670|
|11|19747|13.07985|
|12|19777|13.44919|
|13|19939|13.56673|
|15|20040|13.82602|
|16|21261|13.254|
|17|21332|15.160|
|18 DIFFERENT RATE|21906|21.92|
|20|36061|30.886|
|21|36454|21.606|
Cycle14 missing, numbering per author. Cycle18 at 0.005C, not comparable to ~3A series; exclude from same-rate trend. 17100 rest 36d after charge, with changing sampled SG; next discharge 26.026 vs29.809, no recovery. Mean author density at intermediate point inconsistent with six listed values (1.3015 vs1.306); no spatial SG proof. 25860 approximate 13.5Ah ->18.739 after months; 25871 after34 days buffer/storage 22.49812Ah at3A/10.5V, author charger count47.9Ah. Difference from18.739 is3.75912Ah, not claimed3.868. 28929 after further cycling 16.621Ah, tester589A EN and OCV13.02; 36024 137 days vehicle use then staged charge, 36061 30.886 (Q25 31.664), 36454 21.606 (Q25 21.996). Rebound +85.82%, next −30.05%; not durable repair or isolated rest effect. No independent control. Tester readings not a standard cold crank test. 20129 separately reports 615A tester vs13.5Ah, not exact aligned measurement.
## TG10 extension: Tyumen AGM
13 earlier discharge observations cycles33–45 and previously missing70 (46480 31.546Ah); no validated starting capacity. Cycle35 23.796Ah (37467), ~38 days discharged rest (38936), charge58.287Ah and ~95 days storage (42921), then 43.169Ah top-up and intermediate 1Ah discharge (42976); cycle36 43.391Ah (43013), +82.35%. Not isolated rest. 43887 duplicate charge numbering; map chronologically not by label alone. 45920 reported heating to44C during charge67 despite decreasing current; next discharge 33.111 vs34.831. 46046 reports heating again and water addition; 46091 33.823Ah, intervention confounded. No recommendation to open or manipulate VRLA, no claim confirmed thermal runaway mechanism. Relevant safety finding: decreasing I alone cannot rule out rising T; independent T monitoring and stop criteria needed, no universal threshold derived.
## External cross-check and protocol implications
EN50342-6:2025 public catalog https://www.iteh.us/catalog/standards/clc/02d92508-1cf9-4609-88d1-4f6e72309caf/en-50342-6-2025 and ANSI preview index https://webstore.ansi.org/preview-pages/DS/preview_M382009CURES.pdf : endurance/microcycle testing, temperature and rest prescribed; preview only, not full compliance claim. 2024 charge time paper https://doi.org/10.3390/batteries10060201 indexed text only; full publisher page HTTP429; no quantitative extraction. Rapid partial charging https://www.sciencedirect.com/science/article/pii/S0378775396025098 indexed abstract: capacity recovered after extended recharge under tested VRLA partial-charge cycling; not direct verification of forum mechanism. Prior PNNL 2022 report25 is independent context, not new cohort. Lithium-ion rest-recovery studies excluded from Pb evidence.
Protocol draft: distinguish matched reference Q from operational Q, log discharge I/Ucut/T and actual preconditioning, integrate signed Ah independently, define matched rest vs recharge vs normal use controls, repeated standardized capacity after intervention and at fixed follow-ups, track cumulative Ah throughput/EFC only with known nominal and complete cycle history, report all missing cycles and instrument failures. Include prespecified temperature and manufacturer limits, never infer safe thresholds from forum logs. No new scientific gate; E4 observations, C192/H93, 62/88. No physical experiments or RD6018 changes.
## Provenance
Links https://t.me/UklonGroup/<message ID>; local cache not public. Selected images downloaded, not visually validated; underlying time series and calibration remain open. Report51 counts unchanged historically. Next: independently validate author spreadsheet if publicly accessible, reconcile image traces and full cycle series, then S5 metrology/protocol work.
