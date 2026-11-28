from pathlib import Path
import struct,zlib,zipfile,collections,math
ROOT=Path(r'<RESEARCH_ROOT>')
ZIP=ROOT/'sources/R20/Kwiecien_2018_supplement_alt.zip'
def elems(b):
 i=0
 while i+8<=len(b):
  t,n=struct.unpack_from('<II',b,i)
  if t>>16:
   n=t>>16;t=t&65535
   assert n<=4
   yield t,b[i+4:i+4+n];i+=8
  else:
   assert i+8+n<=len(b),(t,n,len(b),i)
   yield t,b[i+8:i+8+n]
   i+=8+n if t==15 else 8+(n+7)//8*8
def matrix(b):
 e=list(elems(b));cls=struct.unpack_from('<I',e[0][1])[0]&255
 dims=struct.unpack('<'+'i'*(len(e[1][1])//4),e[1][1]);name=e[2][1].decode('ascii','replace')
 if cls==2:
  assert math.prod(dims)==1
  w=struct.unpack_from('<i',e[3][1])[0]
  fields=[e[4][1][i:i+w].split(b'\0')[0].decode() for i in range(0,len(e[4][1]),w)]
  return name,{k:matrix(v)[1] for k,(t,v) in zip(fields,e[5:])}
 if cls==4:return name,e[3][1]
 if len(e)<4:return name,()
 t,v=e[3]
 fm={1:'b',2:'B',3:'h',4:'H',5:'i',6:'I',7:'f',9:'d',12:'q',13:'Q'}.get(t)
 if not fm:return name,None
 return name,struct.unpack('<'+fm*(len(v)//struct.calcsize(fm)),v)
def mat(b):
 assert b[126:128]==b'IM'
 out={}
 for t,v in elems(b[128:]):
  if t==15:
   for t2,v2 in elems(zlib.decompress(v)):
    if t2==14:
     k,x=matrix(v2);out[k]=x
  elif t==14:
   k,x=matrix(v);out[k]=x
 return out
import re, statistics, hashlib
from collections import Counter
targets=(1000,10,0.1)
records={}; parse_errors=[]; missing=Counter(); all_count=0
with zipfile.ZipFile(ZIP) as z:
 names=[n for n in z.namelist() if '/EISData/' in n and n.endswith('.mat')]
 print('ARCHIVE',hashlib.sha256(ZIP.read_bytes()).hexdigest())
 for n in names:
  try:
   d=mat(z.read(n))['eisMeter']; f=d['ActFreq_Hz']; x=d['Zreal_whole_Ohm']; y=d['Zimg_whole_Ohm']
   assert len(f)==len(x)==len(y)
   all_count+=1
  except Exception as e:
   parse_errors.append((n,str(e)));continue
  m=re.search(r'/([^/]+)/CheckUp_(\d+)cycles_25deg/EISData/[^/]*EIS-3I20_1_(80per|aftCHA|aftCyc)\.mat$',n)
  if not m:continue
  key=(m[1],int(m[2]),m[3]);assert key not in records,key
  vals=[]
  for target in targets:
   valid=[(i,ff) for i,ff in enumerate(f) if ff>0 and math.isfinite(ff) and math.isfinite(x[i]) and math.isfinite(y[i]) and (x[i]!=0 or y[i]!=0)]
   if not valid: vals.append(None);missing[target]+=1;continue
   i,ff=min(valid,key=lambda p:abs(math.log(p[1]/target)))
   if abs(math.log(ff/target))>math.log(1.25):vals.append(None);missing[target]+=1
   else: vals.append((ff,math.hypot(x[i],y[i])))
  records[key]=vals
print('PARSED',all_count,'ERRORS',len(parse_errors),'CHECKUPS',len(set((k[0],k[1]) for k in records)),'SELECTED',len(records),'MISSING',dict(missing))
for error in parse_errors[:3]: print('ERROR',error)
for cell in sorted(set(k[0] for k in records)):
 a=records.get((cell,0,'80per'));b=records.get((cell,90,'80per'))
 if a and b:
  print('90FCE/0FCE',cell,[(round(y[0],3),round(y[1]/x[1],4)) if x and y else None for x,y in zip(a,b)])
 pairs=[(v,records[(c,n,'aftCHA')]) for (c,n,phase),v in records.items() if c==cell and phase=='aftCyc' and (c,n,'aftCHA') in records]
 for j,t in enumerate(targets):
  ratios=[a[j][1]/b[j][1] for b,a in pairs if a[j] and b[j]]
  print('POST/PRE',cell,t,'n',len(ratios),'median',round(statistics.median(ratios),4) if ratios else None,'lower',sum(x<1 for x in ratios))
assert all_count==2104 and not parse_errors
print('RAW_PARSE_PASS; preliminary unfiltered magnitudes only, no zHit, no capacity model or chemical diagnosis')
