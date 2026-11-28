"""Staged public Oxford data acquisition, research only; no equipment."""
from pathlib import Path
import urllib.request,hashlib,zipfile,time,concurrent.futures
root=Path(__file__).resolve().parents[1]/'sources'/'R20'
base='https://ora.ox.ac.uk/objects/uuid:e41d3d4c-f74e-4d76-81fd-0caa77ec6cec/files/'
sources=[('BBOXX_set_10.zip','d9g54xh85t'),('BBOXX_GITT_OCV.mpt','dw0892b24g')]
def fetch(x):
 name,ident=x;target=root/name;tmp=target.with_suffix(target.suffix+'.part')
 start=time.monotonic();h=hashlib.sha256();n=0
 try:
  if target.exists():
   print('PRESENT',name,target.stat().st_size,flush=True)
   with target.open('rb') as f:
    while b:=f.read(1024*1024):h.update(b);n+=len(b)
  else:
   with urllib.request.urlopen(base+ident,timeout=8) as f,tmp.open('wb') as out:
    print('RESPONSE',name,f.status,f.headers.get('Content-Type'),f.headers.get('Content-Length'),flush=True)
    while b:=f.read(1024*1024):
     n+=len(b)
     if n>100_000_000 or time.monotonic()-start>45:raise ValueError('bounded download exceeded')
     h.update(b);out.write(b)
   if name.endswith('.zip'):
    with zipfile.ZipFile(tmp) as z:assert z.testzip() is None
   else:
    with tmp.open('rb') as f:assert f.read(30).startswith(b'EC-Lab ASCII FILE')
   tmp.replace(target)
  return h.hexdigest()+'  '+name,n
 except Exception as e:
  print('NOT_ARCHIVED',name,str(e),flush=True)
  if tmp.exists():tmp.unlink()
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:rows=[x for x in pool.map(fetch,sources) if x]
p=root/'SHA256SUMS.txt';old=p.read_text(encoding='utf8') if p.exists() else ''
p.write_text(old.rstrip()+'\n'+'\n'.join(x for x,n in rows if x not in old)+'\n',encoding='utf8')
for x,n in rows:print('ARCHIVED',x,n,flush=True)
print('S3_ACQUISITION_COMPLETE',len(rows),'of',len(sources))
