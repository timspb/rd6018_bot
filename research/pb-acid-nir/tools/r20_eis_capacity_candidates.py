"""Screen logged -2 A discharges ending near 1.8 V; candidate labels, not a verified checkup mapping."""
from pathlib import Path
import zipfile,runpy,contextlib,io,math
root=Path(__file__).resolve().parents[1]
with contextlib.redirect_stdout(io.StringIO()):
 d=runpy.run_path(str(root/'tools/r20_eis_raw_audit.py'))
with zipfile.ZipFile(d['ZIP']) as z:
 count=0
 for n in z.namelist():
  if not n.endswith('.mat') or '/EISData/' in n:continue
  tr=d['mat'](z.read(n))['digatron'];t=tr['time_sec'];i=tr['current_A'];u=tr['voltage_V'];temp=tr['temperature_celcius']
  # exclude short mini-cycles by duration and verify actual end voltage
  seg=[];start=None
  for j,x in enumerate(i):
   yes=abs(x+2)<.05
   if yes and start is None:start=j
   if not yes and start is not None:
    end=j-1
    if t[end]-t[start]>600 and u[end]<=1.83:
     q=-sum((i[k]+i[k+1])/2*(t[k+1]-t[k])/3600 for k in range(start,end))
     seg.append((round(t[start]/3600,2),round(q,4),round(u[end],3),round(temp[start],1),round(temp[end],1)))
    start=None
  count+=len(seg)
  print(n.split('/')[2],n.split('/')[3],n.split('/')[-1],seg)
 print('CANDIDATE_DISCHARGES',count)
