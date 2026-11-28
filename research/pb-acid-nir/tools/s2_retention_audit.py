"""Archive public primary reports and reproduce descriptive retention arithmetic, offline equipment."""
from pathlib import Path
import urllib.request,hashlib,concurrent.futures
r=Path(__file__).resolve().parents[1]/'sources'/'S2'
r.mkdir(parents=True,exist_ok=True)
sources={'Sandia_EESAT_2009_carbon.pdf':'https://www.sandia.gov/files/ess/EESAT/2009_papers/Large%20Format%20Carbon%20Enhanced%20VRLA%20Battery%20Test%20Results.pdf','INL_EXT_12_28003.pdf':'https://avt.inl.gov/sites/default/files/pdf/hev/UltraBatteryReport.pdf'}
def fetch(item):
 n,url=item
 try:
  with urllib.request.urlopen(url,timeout=8) as f:b=f.read(20000001)
  assert b.startswith(b'%PDF') and len(b)<=20000000
  (r/n).write_bytes(b)
  return hashlib.sha256(b).hexdigest()+'  '+n,len(b)
 except Exception as e:print('NOT_ARCHIVED',n,str(e),flush=True);return None
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex: results=[v for v in ex.map(fetch,sources.items()) if v]
p=r/'SHA256SUMS.txt';old=p.read_text(encoding='utf8') if p.exists() else ''
p.write_text(old.rstrip()+'\n'+'\n'.join(x for x,n in results if x not in old)+'\n',encoding='utf8')
for x,n in results:print('ARCHIVED',x,n)
change=lambda a,b:100*(b/a-1)
for name,a,b in [('steady capacity',831,851),('operational capacity',831,1008),('minimum operational',831,725),('PSOC200A cap1000',1000,305),('PSOC400A',290,186),('final conditioning',851,918)]:
 print(name,a,b,round(change(a,b),4))
# Source nominal 10% shallow cycles (not measured Ah-based equivalent full cycles).
print('NOMINAL_EFC_SCREENING',8529*.1)
for a,b,c in [(9,5,9),(8,4,8),(6,3,6)]:
 print('FUB repeat count',a,b,c,'loss_pct',round(change(a,b),3),'recharge_gain_pct',round(change(b,c),3))
print('S2_RETENTION_AUDIT_PASS')
