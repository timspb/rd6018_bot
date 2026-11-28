"""Compare all original MAT numeric fields using scipy.io.loadmat vs legacy decoder."""
from pathlib import Path
import sys,runpy,io,contextlib,zipfile,collections,math
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'tools/.eis-scipy'))
import scipy,numpy as np
from scipy.io import loadmat
print('VERSIONS',scipy.__version__,np.__version__,flush=True)
with contextlib.redirect_stdout(io.StringIO()):
 d=runpy.run_path(str(root/'tools/r20_eis_raw_audit.py'))
counts=collections.Counter(); fields=collections.Counter(); strings=collections.Counter(); errors=[];ranges={};examples={}
with zipfile.ZipFile(d['ZIP']) as z:
 for n in z.namelist():
  if not n.endswith('.mat'):continue
  raw=z.read(n)
  try:
   a=d['mat'](raw)
   b=loadmat(io.BytesIO(raw),struct_as_record=False,squeeze_me=True)
   for k,v in a.items():
    if not isinstance(v,dict):continue
    x=b[k]
    assert set(v)==set(x._fieldnames),(k,set(v)^set(x._fieldnames))
    counts[k]+=1
    if k not in examples:examples[k]=(n,list(v))
    for field,y in v.items():
     w=getattr(x,field); arr=np.asarray(w)
     fields[(k,field)]+=1
     if arr.dtype.kind in 'biuf' and isinstance(y,tuple):
      aa=np.asarray(y).reshape(-1);bb=arr.reshape(-1,order='F')
      assert aa.size==bb.size,(field,aa.size,bb.size)
      assert np.array_equal(aa,bb,equal_nan=True),(field,'value mismatch')
      counts['numeric_fields']+=1;counts['numeric_values']+=aa.size
      if k=='eisMeter' and field in ('ActFreq_Hz','Zreal_whole_Ohm','Zimg_whole_Ohm'):
       vals=bb[np.isfinite(bb)]
       if vals.size:
        key=field;old=ranges.get(key,(math.inf,-math.inf))
        ranges[key]=(min(old[0],float(vals.min())),max(old[1],float(vals.max())))
     elif arr.dtype.kind in 'US' or isinstance(y,bytes):
      strings[(k,field)]+=1
      counts['text_fields_not_compared']+=1
     else:
      counts['other_fields_not_compared']+=1
   counts['files']+=1
  except Exception as e:
   errors.append((n,str(e)))
 print('AUTHOR_SCRIPTS',[n for n in z.namelist() if n.endswith('.m')][:60])
 for n in z.namelist():
  if n.endswith('/plotEIS.m') or n.endswith('/zHit.m'):
   print('AUTHOR_CODE',n)
   for i,l in enumerate(z.read(n).decode('latin1').splitlines(),1):
    if any(t in l.lower() for t in ['ohm','zhit','time','0.15','1000','1e3','1e-3']):
     print(i,l[:180])
print('COUNTS',dict(counts),'ERRORS',len(errors),'FIRST',errors[:5])
print('SCHEMA_EXAMPLES',examples)
print('TEXT_FIELDS',dict(strings))
print('FIELD_COUNTS',dict(fields))
print('NUMERIC_RANGES',ranges)
assert not errors and counts['eisMeter']==2104 and counts['digatron']==38
print('S3_INDEPENDENT_NUMERIC_DECODER_PASS; text metadata excluded')
