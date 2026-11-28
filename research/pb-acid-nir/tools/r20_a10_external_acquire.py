from pathlib import Path
import urllib.request,hashlib,zipfile,io,concurrent.futures,csv
r=Path(__file__).resolve().parents[1]/'sources'/'R20'
items=[('OPzS_Cell_'+str(i)+'.zip','https://zenodo.org/records/17252822/files/Cell%20'+str(i)+'.zip?download=1',h) for i,h in enumerate(['2410cefe271a8d08c591d5f239c464b3','a25d6ee702f8d86d8e1c0ed6d06cdd8f','47ae161ec4966e4177d709f9d3127361','8de86b243d7744a279b35608a358299b','0be20d039145fab5219fa5f1c7351c23','ea99f945a88bc9654db8fb00fa4d7fab'],1)]
items += [('OPzS_description.pdf','https://zenodo.org/records/17252822/files/DATASET%20DESCRIPTION.pdf?download=1','e514395c423d4e0ff5a0855e6ba364dc'),('BBOXX_meta_data.csv','https://ora.ox.ac.uk/objects/uuid:e41d3d4c-f74e-4d76-81fd-0caa77ec6cec/files/dtd96k277p',None),('BBOXX_readme.txt','https://ora.ox.ac.uk/objects/uuid:e41d3d4c-f74e-4d76-81fd-0caa77ec6cec/files/rkw52j8536',None)]
def fetch(x):
 name,url,md5=x
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Pb-Research academic data access'}),timeout=12) as f:
   b=f.read(10_000_001)
  assert len(b)<=10_000_000
  if md5:assert hashlib.md5(b).hexdigest()==md5,'publisher MD5 mismatch'
  if name.endswith('.zip'):
   with zipfile.ZipFile(io.BytesIO(b)) as z:
    assert z.testzip() is None
    print(name,'members',len(z.namelist()),z.namelist()[:3],flush=True)
  elif name.endswith('.pdf'):assert b.startswith(b'%PDF')
  else:assert not b.lstrip().lower().startswith((b'<html',b'<!doctype')), 'HTML'
  (r/name).write_bytes(b)
  return hashlib.sha256(b).hexdigest()+'  '+name
 except Exception as e: print(name,'NOT_ARCHIVED',type(e).__name__,str(e)[:140],flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:lines=[v for v in ex.map(fetch,items) if v]
p=r/'SHA256SUMS.txt';old=p.read_text(encoding='utf-8') if p.exists() else ''
p.write_text(old.rstrip()+'\n'+'\n'.join(x for x in lines if x not in old)+'\n',encoding='utf-8')
for x in lines:print('ARCHIVED',x)
