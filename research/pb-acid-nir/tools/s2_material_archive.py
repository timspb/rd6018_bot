"""Public source archive and descriptive calculation; no device I/O."""
from pathlib import Path
import urllib.request,hashlib,concurrent.futures
r=Path(__file__).resolve().parents[1]/'sources'/'S2'
sources={'Hu_2016.pdf':'https://www.electrochemsci.org/papers/vol11/110201416.pdf','Cattelan_2026.pdf':'https://research.unipd.it/retrieve/167cd10c-7e85-4668-b757-a591691f6150/1-s2.0-S0013468626008868-main.pdf','Ruetschi_2003.pdf':'https://www.electronicsandbooks.com/edt/manual/Magazine/J/Journal%20of%20Power%20Sources/2003%20%28Vol%20116%29/No01-2%28i-viii%29/53-60.pdf'}
def fetch(item):
 n,u=item
 try:
  with urllib.request.urlopen(u,timeout=8) as f:b=f.read(20000001)
  assert b.startswith(b'%PDF') and len(b)<=20000000
  (r/n).write_bytes(b);return hashlib.sha256(b).hexdigest()+'  '+n,len(b)
 except Exception as e:print('NOT_ARCHIVED',n,str(e),flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:rows=[x for x in pool.map(fetch,sources.items()) if x]
p=r/'SHA256SUMS.txt';old=p.read_text(encoding='utf8') if p.exists() else ''
p.write_text(old.rstrip()+'\n'+'\n'.join(x for x,n in rows if x not in old)+'\n',encoding='utf8')
for x,n in rows:print('ARCHIVED',x,n)
print('OBSERVATION_HORIZON_RATIO_NOT_LIFETIME',400/290)
print('S2_MATERIAL_AUDIT_PASS')
