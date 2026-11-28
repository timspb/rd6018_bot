"""Exploratory grouped validation of residual after-cycling capacity, not fully charged C20."""
from pathlib import Path
import runpy,contextlib,io,sys,zipfile,re,statistics,math
root=Path(__file__).resolve().parents[1]
sys.argv=[str(root/'tools/r20_eis_zhit_audit.py'),'-1']
with contextlib.redirect_stdout(io.StringIO()):
 a=runpy.run_path(sys.argv[0])
d=a['d']; q={}
with zipfile.ZipFile(d['ZIP']) as z:
 for n in z.namelist():
  if not n.endswith('.mat') or '/EISData/' in n:continue
  m=re.search(r'/([^/]+)/CheckUp_(\d+)cycles_25deg/',n)
  if not m or int(m[2])==0:continue
  tr=d['mat'](z.read(n))['digatron'];t=tr['time_sec'];i=tr['current_A'];u=tr['voltage_V'];start=None
  for j,x in enumerate(i):
   yes=abs(x+2)<.05
   if yes and start is None:start=j
   if not yes and start is not None:
    end=j-1
    if t[end]-t[start]>600 and 1.77<=u[end]<=1.83:
     key=(m[1],int(m[2]));assert key not in q,key
     q[key]=-sum((i[k]+i[k+1])/2*(t[k+1]-t[k])/3600 for k in range(start,end))
    start=None
print('NONBASELINE_Q',len(q))
rows=[]
for (cell,cy,mini,phase),v in a['selections'].items():
 if mini!=1 or phase!='aftCyc' or (cell,cy) not in q:continue
 if all(v[j][2] for j in (0,1)):rows.append((cell,cy,q[cell,cy],v[0][1],v[1][1]))
print('COMPLETE_CASE',len(rows),'cells',len(set(r[0] for r in rows)))
for cell in sorted(set(r[0] for r in rows)):
 train=[r for r in rows if r[0]!=cell];test=[r for r in rows if r[0]==cell]
 errors=[]
 for idx in (1,3,4):
  slope,inter=statistics.linear_regression([r[idx] for r in train],[r[2] for r in train])
  errors.append(round(statistics.mean(abs(slope*r[idx]+inter-r[2]) for r in test),3))
 print('HELD_OUT',cell,len(test),'MAE_Ah cycles,1kHz,10Hz',errors)
print('EXPLORATORY_ONLY, n=4 cells; capacity after cycling, not fully charged SOH; no tuning')
