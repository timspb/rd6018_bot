"""Independent Python transcription of the one-gamma zHit formula in the author's supplement.
No device I/O. Native numeric units retained; absolute tolerance 0.15 is from author plot.
"""
from pathlib import Path
import zipfile,runpy,contextlib,io,math,re,statistics,collections,sys
bias=sys.argv[1] if len(sys.argv)>1 else '-3'
assert bias in ('-1','-3')
print('SELECTED_BIAS',bias+'I20')
root=Path(__file__).resolve().parents[1]
with contextlib.redirect_stdout(io.StringIO()):
 d=runpy.run_path(str(root/'tools/r20_eis_raw_audit.py'))
def zhit(f,z):
 w=[math.log(2*math.pi*x) for x in f]
 ph=[math.atan2(x.imag,x.real) for x in z]
 a=[abs(x) for x in z]
 integ=[0.]*len(w)
 for i in range(len(w)-2,-1,-1): integ[i]=integ[i+1]-(w[i+1]-w[i])*(ph[i+1]+ph[i])/2
 h=[2/math.pi*integ[i]-math.pi/6*((ph[i]-ph[i-1])/(w[i]-w[i-1])+(ph[i+1]-ph[i])/(w[i+1]-w[i]))/2 for i in range(1,len(w)-1)]
 c=statistics.mean(math.log(a[i])-h[i-1] for i in range(1,len(w)-1))
 return [None]+[math.exp(c+x) for x in h]+[None]
# analytic series RC, wide frequency range; approximate formula not exact
f=[10**(5-i*.125) for i in range(81)]
z=[3+5/(1+2j*math.pi*x*.02) for x in f]
pred=zhit(f,z)
print('SYNTHETIC_RC_MEDIAN_REL_ERROR',statistics.median(abs(abs(v)-p)/abs(v) for v,p in zip(z,pred) if p is not None))
counts=collections.Counter(); selections={}; traces=[]
with zipfile.ZipFile(d['ZIP']) as archive:
 for n in archive.namelist():
  if not n.endswith('.mat'):continue
  v=d['mat'](archive.read(n))
  if '/EISData/' not in n:
   tr=v['digatron'];t=tr['time_sec'];i=tr['current_A'];u=tr['voltage_V']
   assert len(t)==len(i)==len(u)
   counts['traces']+=1
   counts['trace_rows']+=len(t)
   counts['time_decreases']+=sum(b<a for a,b in zip(t,t[1:]))
   if n.endswith('fstCheck.mat') and len(traces)<4:
    # descriptive contiguous -0.5A plateaus, no capacity label until source program verified
    seg=[];start=None
    for j,x in enumerate(i):
     yes=abs(x+.5)<.025
     if yes and start is None:start=j
     if not yes and start is not None:
      if t[j-1]-t[start]>3600:seg.append((round(t[start]/3600,3),round((t[j-1]-t[start])/3600,3),round(u[j-1],3),round(-sum((i[k]+i[k+1])/2*(t[k+1]-t[k])/3600 for k in range(start,j-1)),4)))
      start=None
    traces.append((n.split('/')[2],seg))
   continue
  counts['spectra']+=1
  v=v['eisMeter']; fs=v['ActFreq_Hz']; re_=v['Zreal_whole_Ohm']; im=v['Zimg_whole_Ohm']
  # Whole-cell direct channels; last adjacent duplicate retained; not exact electrode subtraction mask.
  p=[]
  for f,a,b in zip(fs,re_,im):
   if f<=0 or not all(math.isfinite(k) for k in (f,a,b)) or a==0 or b==0:continue
   if p and p[-1][0]==f:p[-1]=(f,complex(a,b));counts['duplicate_adjacent']+=1
   else:p.append((f,complex(a,b)))
  if len(p)<5 or any(b[0]>=a[0] for a,b in zip(p,p[1:])):
   counts['excluded_order_or_length']+=1;continue
  f,z=zip(*p);pred=zhit(f,z);counts['zhit_computed']+=1
  for k,est in enumerate(pred):
   if est is None:continue
   counts['interior_points']+=1
   if abs(abs(z[k])-est)<.15:counts['author_abs_pass']+=1
  m=re.search(r'/([^/]+)/CheckUp_(\d+)cycles_25deg/EISData/[^/]*EIS'+re.escape(bias)+r'I20_([12])_(80per|aftCHA|aftCyc)\.mat$',n)
  if not m:continue
  key=(m[1],int(m[2]),int(m[3]),m[4]);assert key not in selections
  out=[]
  for target in (1000,10,.1):
   k=min(range(len(f)),key=lambda k:abs(math.log(f[k]/target)))
   ok=pred[k] is not None and abs(math.log(f[k]/target))<=math.log(1.25) and abs(abs(z[k])-pred[k])<.15
   out.append((f[k],abs(z[k]),ok))
  selections[key]=out
print('COUNTS',dict(counts))
print('TRACE_CANDIDATES',traces)
for j,target in enumerate((1000,10,.1)):
 vals=[v[j] for v in selections.values()]
 pairs=[]
 for (cell,cy,mini,phase),v in selections.items():
  if mini!=1:continue
  u=selections.get((cell,cy,2,phase))
  if u and v[j][2] and u[j][2] and v[j][0]==u[j][0]:
   pairs.append(abs(u[j][1]/v[j][1]-1)*100)
 print('TARGET',target,'pass',sum(v[2] for v in vals),'of',len(vals),'repeat_pairs',len(pairs),'median_abs_pct',round(statistics.median(pairs),3) if pairs else None,'max_pct',round(max(pairs),3) if pairs else None)
 for cell in sorted(set(k[0] for k in selections)):
  ratios=[]
  for (c,cy,mini,phase),v in selections.items():
   if c!=cell or mini!=1 or phase!='aftCyc':continue
   u=selections.get((c,cy,mini,'aftCHA'))
   if u and v[j][2] and u[j][2] and v[j][0]==u[j][0]:ratios.append(u[j][1]/v[j][1])
  if ratios: print('FILTERED_POST_PRE',cell,target,len(ratios),round(statistics.median(ratios),4))
print('ZHIT_SCREEN_COMPLETE; native absolute tolerance, direct whole-cell channels, not certified validity')
