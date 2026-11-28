"""Audit public field outcome metadata; no telemetry or capacity labels inferred."""
from pathlib import Path
import csv,statistics,collections
p=Path(__file__).resolve().parents[1]/'sources/R20/BBOXX_meta_data.csv'
with p.open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
assert len(rows)==len(set(r['ID'] for r in rows))==1027
for alive in ['TRUE','FALSE']:
 a=[r for r in rows if r['STILL_ALIVE']==alive]
 d=[float(r['Lifetime']) for r in a]
 print('STILL_ALIVE',alive,'N',len(a),'days min/median/max',min(d),statistics.median(d),max(d),'repair_date_missing',sum(not r['IN_REPAIR_SYSTEM'] for r in a))
print('METADATA_PASS; outcome selection and censoring, no prevalence, no C20 or mechanism labels')
