"""Read-only schema and internal consistency audit; no device I/O."""
from pathlib import Path
import csv,zipfile,collections,datetime,math
r=Path(__file__).resolve().parents[1]/'sources'/'R20'
num=lambda x:float(x.strip().replace(',','.'))
counts=collections.Counter();headers=set();bank={}
for p in sorted(r.glob('OPzS_Cell_*.zip')):
 cell=int(p.stem.split('_')[-1]); timestamps={};duplicate=0
 with zipfile.ZipFile(p) as z:
  for n in z.namelist():
   if not n.endswith('.csv'):continue
   counts['files']+=1;prior=None
   rd=csv.reader(z.read(n).decode('cp1252').splitlines(),delimiter=';')
   head=next(rd);headers.add(tuple(head[:7]))
   counts['header_extra']+=len(head)>7
   if not head[3].startswith('T'+str(cell)+' '):print('TEMP_HEADER_MISMATCH',n,head[3])
   for line in rd:
    if not line or not any(line):continue
    counts['rows']+=1
    try:
     assert len(line)>=7
     if len(line)>7:
      counts['extra_column_rows']+=1
      if any(x.strip() for x in line[7:]):counts['nonempty_extras']+=1;raise ValueError('nonempty extra columns')
      line=line[:7]
     t=datetime.datetime.strptime(line[0],'%d/%m/%Y %H:%M')
     mv,v,T,I,Ah=map(num,line[1:6]);soc=num(line[6].strip().removesuffix('%'))
     assert all(math.isfinite(x) for x in (mv,v,T,I,Ah,soc))
    except Exception as e:
     counts['invalid']+=1
     if counts['invalid']<=5:print('INVALID_EXAMPLE',n,line[:8],str(e))
     continue
    counts['mv_v_agree']+=abs(mv/1000-v)<=.00002
    counts['soc_Ah_agree']+=abs(Ah/12-soc)<=.02
    if prior is not None:
     dt=(t-prior).total_seconds()
     counts['step_60s']+=dt==60
     counts['step_other']+=dt!=60
    prior=t
    if t in timestamps:
     duplicate+=1
     if timestamps[t]!=I:counts['duplicate_current_conflict']+=1;timestamps[t]=None
    else:timestamps[t]=I
 bank[cell]=timestamps
 print('CELL',cell,'timestamps',len(timestamps),'duplicate',duplicate)
common=set.intersection(*(set(x) for x in bank.values()))
valid_common=[t for t in common if all(bank[c][t] is not None for c in bank)]
same=sum(max(bank[c][t] for c in bank)-min(bank[c][t] for c in bank)<=.01 for t in valid_common)
print('COUNTS',dict(counts));print('HEADER_VARIANTS',len(headers));print('ALL6_COMMON',len(common),'UNAMBIGUOUS_CURRENT',len(valid_common),'CURRENT_AGREEMENT',same)
print('SCHEMA_AUDIT_COMPLETE; SOC arithmetic check not independent capacity ground truth')
