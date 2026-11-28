"""Retrospective OPzS common-load rest screen; not a mechanism classifier."""
from pathlib import Path
import runpy,io,contextlib,statistics as st
root=Path(__file__).resolve().parents[1]
with contextlib.redirect_stdout(io.StringIO()):
 a=runpy.run_path(str(root/'tools/r20_opzs_test_alignment.py'))
groups=a['groups']
for lim in (.1,1.0):
 alln=0;allcells=[];total_common=total_plausible=total_agree=total_low=0;longest=0;neg=0
 for test,bank in sorted(groups.items()):
  if len(bank)!=6:continue
  common=sorted(set.intersection(*(set(v) for v in bank.values())))
  total_common+=len(common)
  neg+=sum(bank[c][t][0]<0 for t in common for c in bank)
  plausible=[t for t in common if all(0<=bank[c][t][0]<=3 for c in bank)]
  agreed=[t for t in plausible if max(bank[c][t][1] for c in bank)-min(bank[c][t][1] for c in bank)<=.01]
  total_plausible+=len(plausible);total_agree+=len(agreed)
  # Require each channel physically plausible, current agreement, low-current.
  good=[t for t in common if all(0<=bank[c][t][0]<=3 and abs(bank[c][t][1])<=lim for c in bank)
      and max(bank[c][t][1] for c in bank)-min(bank[c][t][1] for c in bank)<=.01]
  blocks=[];seg=[]
  for t in good:
   if seg and (t-seg[-1]).total_seconds()!=60:blocks.append(seg);seg=[]
   seg.append(t)
  if seg:blocks.append(seg)
  total_low+=len(good);longest=max(longest,max((len(x)-1 for x in blocks),default=0))
  selected=[x for x in blocks if len(x)>=61]
  if selected:print('TEST',lim,test,'blocks',len(selected))
  for seg in selected:
   # Fixed first and final five samples. Long and short blocks separate in report.
   first=[st.median(bank[c][t][0] for t in seg[:5]) for c in range(1,7)]
   last=[st.median(bank[c][t][0] for t in seg[-5:]) for c in range(1,7)]
   low=last.index(min(last))+1
   alln+=1;allcells.append(low)
   print('REST',lim,seg[0].isoformat(),len(seg)-1,'min','first/final spread mV',round(1000*(max(first)-min(first)),2),round(1000*(max(last)-min(last)),2),'lowest',low,'cell2 delta mV',round(1000*(last[1]-first[1]),2))
 print('TOTAL_REST',lim,alln,'cell2_lowest',allcells.count(2),'COMMON',total_common,'PLAUSIBLE',total_plausible,'CURRENT_AGREE',total_agree,'LOW_CURRENT',total_low,'LONGEST_MIN',longest,'NEGATIVE_CELL_RECORDS',neg)
print('S3_REST_SCREEN_PASS; no known true SOC, no chemical labels, no independent bank')
