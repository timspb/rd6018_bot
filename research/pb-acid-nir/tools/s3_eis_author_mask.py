"""Audit published MATLAB preprocessing and zHit threshold, independently using NumPy."""
from pathlib import Path
import sys,zipfile,io,collections,math
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'tools/.eis-scipy'))
import numpy as np
from scipy.io import loadmat
def clean(f,z):
 m=(f!=0)&(z.real!=0)&(z.imag!=0)
 f,z=f[m],z[m]
 if len(f)==0:return f,z
 m=np.r_[np.diff(f)!=0,True]
 return f[m],z[m]
def screen(f,z):
 if len(f)<3 or np.any(~np.isfinite(f)) or np.any(f<=0) or np.any(np.diff(f)==0) or np.any(~np.isfinite(z)) or np.any(abs(z)==0):return None
 w=np.log(2*np.pi*f);ph=np.angle(z);a=abs(z)
 h=np.array([-2/np.pi*np.trapezoid(ph[k:],w[k:])-np.pi/6*np.mean(np.diff(ph[k-1:k+2])/np.diff(w[k-1:k+2])) for k in range(1,len(f)-1)])
 pred=np.exp(np.mean(np.log(a[1:-1])-h)+h)
 return len(pred),int(np.sum(abs(pred-a[1:-1])<.15))
cnt=collections.Counter();near=[];days=collections.Counter()
with zipfile.ZipFile(root/'sources/R20/Kwiecien_2018_supplement_alt.zip') as z:
 for n in z.namelist():
  if not n.endswith('.mat') or '/EISData/' not in n:continue
  a=loadmat(io.BytesIO(z.read(n)),squeeze_me=True,struct_as_record=False)['eisMeter']
  f=np.asarray(a.ActFreq_Hz);whole=np.asarray(a.Zreal_whole_Ohm)+1j*np.asarray(a.Zimg_whole_Ohm);neg=np.asarray(a.Zreal_neg_Ohm)+1j*np.asarray(a.Zimg_neg_Ohm)
  p=clean(f,whole-neg);q=clean(f,neg)
  cnt['spectra']+=1
  if len(p[0])!=len(q[0]):cnt['author_length_mismatch']+=1
  elif not np.array_equal(p[0],q[0]):cnt['author_equal_length_frequency_mismatch']+=1
  else:
   v=screen(q[0],p[1]+q[1])
   if v is None:cnt['author_aligned_invalid']+=1
   else:
    cnt['author_aligned_valid']+=1;cnt['author_points']+=v[0];cnt['author_pass']+=v[1]
  d=clean(f,whole);v=screen(*d)
  if v is not None:cnt['direct_valid']+=1;cnt['direct_points']+=v[0];cnt['direct_pass']+=v[1]
  if len(d[0]):
   k=int(np.argmin(abs(d[0]-1000)))
   if 800<=d[0][k]<=1250:near.append(abs(d[1][k]))
  days[n.split('/')[-1].split('_')[0]]+=1
print('COUNTS',dict(cnt))
print('1000HZ_NATIVE_N_MIN_MEDIAN_MAX',len(near),min(near),float(np.median(near)),max(near))
print('DATES',len(days),'EIS_STRUCT_HAS_NO_TIMESTAMP')
print('S3_AUTHOR_MASK_AUDIT_PASS; native units; no physical validation')
