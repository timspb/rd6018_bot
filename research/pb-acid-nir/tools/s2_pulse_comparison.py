"""Descriptive audit of James 2006 Tables 1/3; not an operational waveform."""
from pathlib import Path
import urllib.request,hashlib,statistics as st,concurrent.futures
r=Path(__file__).resolve().parents[1]/'sources'/'S2'
r.mkdir(parents=True,exist_ok=True)
urls={'James_2006.pdf':'https://www.electronicsandbooks.com/edt/manual/Magazine/J/Journal%20of%20Power%20Sources/2006%20%28Vol%20162%29/No02%28749-1470%29/878-883.pdf','Minami_2004.pdf':'https://www.union-services.com/aevs/541-544.pdf'}
def fetch(x):
 n,u=x
 try:
  with urllib.request.urlopen(u,timeout=8) as f:b=f.read(10000001)
  assert b.startswith(b'%PDF') and len(b)<=10000000
  (r/n).write_bytes(b);return f'{hashlib.sha256(b).hexdigest()}  {n}'
 except Exception as e:print('NOT_ARCHIVED',n,str(e),flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:lines=[x for x in pool.map(fetch,urls.items()) if x]
p=r/'SHA256SUMS.txt';old=p.read_text(encoding='utf8') if p.exists() else ''
p.write_text(old.rstrip()+'\n'+'\n'.join(x for x in lines if x not in old)+'\n',encoding='utf8')
for x in lines:print('ARCHIVED',x)
data=[('CC',125,6.83,7.27),('0.5Hz',95,6.97,7.08),('10Hz',80,5.75,5.75),('100Hz',90,5.85,5.11)]
bH=data[0][2]/(400*125/60);bO=data[0][3]/(400*125/60)
for name,t,h,o in data:
 q=400*t/60
 print(name,'approx Ah',round(q,3),'H2 mL/Ah',round(1000*h/q,3),'O2 mL/Ah',round(1000*o/q,3),'relative H2/Ah',round(100*(h/q/bH-1),2),'relative O2/Ah',round(100*(o/q/bO-1),2))
cap=[(101.8,100.7,100),(96.5,100.7,100),(94.5,87.8,99.4),(96.8,95,98.6)]
print('CAPACITY_FINAL_MINUS_FAT_PP',[round(c-a,2) for a,b,c in cap], 'mean',round(st.mean(c-a for a,b,c in cap),2))
print('MANKOV inferred comparators (not measured values)',7.8/1.045,7.8/1.067)
print('S2_AUDIT_PASS')
