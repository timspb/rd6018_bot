"""OPzS test-specific alignment and common-load discharge candidates. Offline, no hardware."""
from pathlib import Path
import zipfile,csv,datetime as dt,collections,statistics as st,math
root=Path(__file__).resolve().parents[1]
r=root/'sources'/'R20'
groups=collections.defaultdict(dict);stats=collections.Counter()
def number(x):return float(x.strip().replace(',','.'))
for p in sorted(r.glob('OPzS_Cell_*.zip')):
 cell=int(p.stem.split('_')[-1])
 with zipfile.ZipFile(p) as z:
  for n in z.namelist():
   if not n.endswith('.csv'):continue
   # Same normalized named test only; merged Cell 1 PV files deliberately excluded.
   test=n.split(' Measurements - ',1)[1].removesuffix('.csv').strip().lower()
   rd=csv.reader(z.read(n).decode('cp1252').splitlines(),delimiter=';');head=next(rd)
   data={};conflict=set()
   for line in rd:
    if not line or not any(line):continue
    try:
     assert len(line)>=7 and not any(x.strip() for x in line[7:])
     t=dt.datetime.strptime(line[0],'%d/%m/%Y %H:%M')
     mv,v=map(number,line[1:3]);I=number(line[4])
     assert all(math.isfinite(x) for x in (mv,v,I)) and abs(mv/1000-v)<=.00002
    except Exception:stats['invalid_voltage_current_rows']+=1;continue
    x=(v,I)
    if t in data and data[t]!=x:conflict.add(t)
    else:data[t]=x
   for t in conflict:data.pop(t,None)
   stats['conflicting_within_test']+=len(conflict)
   assert cell not in groups[test],(test,cell)
   groups[test][cell]=data
print('NAMED_GROUPS',len(groups),'ALL6',sum(len(x)==6 for x in groups.values()),'AUDIT',dict(stats))
for test,bank in sorted(groups.items()):
 if len(bank)!=6:continue
 common=sorted(set.intersection(*(set(v) for v in bank.values())))
 good=[t for t in common if max(bank[c][t][1] for c in bank)-min(bank[c][t][1] for c in bank)<=.01]
 print('ALIGN',test,'common',len(common),'same_I',len(good))
 if 'c20 discharge' not in test and 'c10 discharge' not in test:continue
 # Candidate contiguous nominal-rate blocks; no interpolation across gaps.
 rate=60 if 'c20' in test else 120
 seg=[];parts=[]
 for t in good:
  i=bank[1][t][1]
  if abs(i+rate)>rate*.05 or (seg and (t-seg[-1]).total_seconds()!=60):
   if seg:parts.append(seg);seg=[]
  if abs(i+rate)<=rate*.05:seg.append(t)
 if seg:parts.append(seg)
 for seg in parts:
  if len(seg)<60:continue
  q=-sum((bank[1][a][1]+bank[1][b][1])/120 for a,b in zip(seg,seg[1:]))
  def volts(t):return [bank[c][t][0] for c in range(1,7)]
  start=volts(seg[0]);end=volts(seg[-1]);spread=[max(volts(t))-min(volts(t)) for t in seg]
  print('RATE_BLOCK',test,seg[0].isoformat(),len(seg),'Ah',round(q,2),'sumV_end',round(sum(end),4),'minV_end',round(min(end),5),'end_weak_cell',end.index(min(end))+1,'spread_start/end/max_mV',*[round(1000*x,2) for x in (max(start)-min(start),spread[-1],max(spread))])
print('A11_ALIGNMENT_SCREEN_PASS; candidate nominal-current blocks, not certified capacity tests')

# Explicit audit of impossible-looking voltage records, without silently repairing them.
for test,bank in sorted(groups.items()):
 if len(bank)!=6:continue
 common=sorted(set.intersection(*(set(v) for v in bank.values())))
 weird=[(t,c,bank[c][t][0],bank[c][t][1]) for t in common for c in bank if not 0<=bank[c][t][0]<=3]
 if weird:print('VOLTAGE_OUTSIDE_0_3V',test,'N',len(weird),'EXAMPLES',weird[:4])
