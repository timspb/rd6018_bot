"""Pre-discharge rest and history features, fixed grouped comparisons. No equipment I/O."""
from pathlib import Path
import runpy,contextlib,io,zipfile,re,statistics as st,math,collections
root=Path(__file__).resolve().parents[1]
with contextlib.redirect_stdout(io.StringIO()):
 a=runpy.run_path(str(root/'tools/r20_eis_multifeature.py'))
d=a['a']['d'];predict=a['predict'];rows=[];rejected=[];counts=collections.Counter()
with zipfile.ZipFile(d['ZIP']) as z:
 for n in z.namelist():
  if not n.endswith('.mat') or '/EISData/' in n:continue
  m=re.search(r'/([^/]+)/CheckUp_(\d+)cycles_25deg/',n)
  if not m or int(m[2])==0:continue
  tr=d['mat'](z.read(n))['digatron'];t=tr['time_sec'];i=tr['current_A'];u=tr['voltage_V'];temp=tr['temperature_celcius'];start=None
  for j,x in enumerate(i):
   yes=abs(x+2)<.05
   if yes and start is None:start=j
   if not yes and start is not None:
    end=j-1
    if t[end]-t[start]>600 and 1.77<=u[end]<=1.83:
     counts['candidate']+=1
     k=start-1
     # Permit transition samples between end of zero-current rest and full discharge.
     while k>=0 and abs(i[k])>.005 and t[start]-t[k]<=120:k-=1
     last=k
     while k>=0 and abs(i[k])<=.005:k-=1
     first=k+1
     if last<first or not 14390<=t[last]-t[first]<=14410 or t[start]-t[last]>120:
      rejected.append((m[1],m[2],'rest'));start=None;continue
     # Median windows, entirely before load transition; no post-discharge features.
     def med(v,lo,hi):
      data=[v[h] for h in range(first,last+1) if lo<=t[h]-t[first]<=hi]
      if not data:raise ValueError('missing window')
      return st.median(data)
     early=med(u,600,900);mid=med(u,3600,3900);late=med(u,14100,14410)
     q=-sum((i[h]+i[h+1])/2*(t[h+1]-t[h])/3600 for h in range(start,end))
     # Descriptive prior-record throughput only; not lifetime history.
     prior_pos=sum((max(i[h],0)+max(i[h+1],0))/2*(t[h+1]-t[h])/3600 for h in range(first-1))
     prior_neg=sum((max(-i[h],0)+max(-i[h+1],0))/2*(t[h+1]-t[h])/3600 for h in range(first-1))
     row=(m[1],int(m[2]),q,late,early-late,mid-late,med(temp,14100,14410),prior_pos,prior_neg)
     rows.append(row)
     print('ROW',row[0],row[1],*[round(v,6) for v in row[2:]],'rest_s',round(t[last]-t[first],2),'gap_s',round(t[start]-t[last],2))
    start=None
assert len(set((r[0],r[1]) for r in rows))==len(rows)
print('COUNTS',dict(counts),'included',len(rows),'rejected',rejected)
models=[
 ('FCE OLS',lambda r:[r[1]],0),
 ('FCE ridge',lambda r:[r[1]],1),
 ('Urest OLS',lambda r:[r[3]],0),
 ('Urest+relax ridge',lambda r:[r[3],r[4],r[5]],1),
 ('FCE+Urest ridge',lambda r:[r[1],r[3]],1),
 ('FCE+Urest+relax ridge',lambda r:[r[1],r[3],r[4],r[5]],1),
 ('FCE+Urest+relax+T ridge',lambda r:[r[1],r[3],r[4],r[5],r[6]],1),
 ('FCE+prior Ah ridge',lambda r:[r[1],r[7],r[8]],1),
 ('FCE+all prelabel ridge',lambda r:[r[1],*r[3:]],1)]
a['evaluate'](rows,models)
print('REST_AUDIT_COMPLETE; quasi-OCV after four hours; no equilibrium claim or C20')

# Common subset for directly comparing rest features with the A08 EIS models.
rest={(r[0],r[1]):r for r in rows}
joint=[]
for r in a['rows']:
 v=rest[(r[0],r[1])]
 assert abs(v[2]-r[2])<1e-9
 joint.append((*v,r[3],r[4]))
print('COMMON_EIS_REST',len(joint))
a['evaluate'](joint,[
 ('FCE ridge',lambda r:[r[1]],1),
 ('Urest OLS',lambda r:[r[3]],0),
 ('rest only ridge',lambda r:[r[3],r[4],r[5]],1),
 ('FCE+rest ridge',lambda r:[r[1],r[3],r[4],r[5]],1),
 ('FCE+two-band ridge',lambda r:[r[1],r[9],r[10]],1),
 ('FCE+two-band+rest ridge',lambda r:[r[1],r[9],r[10],r[3],r[4],r[5]],1)])
print('A09_COMMON_CASE_COMPLETE')
