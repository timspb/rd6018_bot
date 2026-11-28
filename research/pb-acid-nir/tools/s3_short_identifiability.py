"""Public original archives and synthetic non-identifiability, no equipment I/O."""
from pathlib import Path
import hashlib,urllib.request,concurrent.futures,math
r=Path(__file__).resolve().parents[1]/'sources'/'S3';r.mkdir(parents=True,exist_ok=True)
urls={'Hitachi_58_advanced.pdf':'https://www.resonac.com/sites/default/files/2022-12/en_pdf-rd-report-058-58_tr02.pdf','Yuasa_2011_008_01_051.pdf':'https://www.gs-yuasa.com/en/technology/technical_report/pdf/vol8/008_01_051.pdf','Yuasa_2023_020_01_014.pdf':'https://www.gs-yuasa.com/en/technology/technical_report/pdf/vol20/020_01_014.pdf'}
def fetch(item):
 n,u=item
 try:
  with urllib.request.urlopen(u,timeout=8) as f:b=f.read(12000001)
  assert b.startswith(b'%PDF') and len(b)<=12000000
  (r/n).write_bytes(b);return hashlib.sha256(b).hexdigest()+'  '+n,len(b)
 except Exception as e:print('NOT_ARCHIVED',n,str(e),flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:rows=[x for x in ex.map(fetch,urls.items()) if x]
p=r/'SHA256SUMS.txt';old=p.read_text(encoding='utf8') if p.exists() else ''
p.write_text(old.rstrip()+'\n'+'\n'.join(x for x,n in rows if x not in old)+'\n',encoding='utf8')
for x,n in rows:print('ARCHIVED',x,n)
# Two unobservable loss mechanisms with identical total loss in a local
# affine OCV model. Example only, not fitted to battery measurements.
for t in (0,1,4,24,72):
 def u(loss,polar):return 2.1-.2*loss*t/35+polar*math.exp(-t/2)
 a=u(.2+.015,.04);b=u(.05+.165,.04)
 assert abs(a-b)<1e-12
 print('SAME_OCV',t,round(a,6))
# Identical terminal sum, different cell distributions.
a=[2.08]*6;b=[2.10]*5+[1.98]
assert abs(sum(a)-sum(b))<1e-12
print('SAME_PACK_V',sum(a), 'MIN_CELL',min(a),min(b))
# Recompute 2023 manufacturer comparative table: life and gravimetric loss.
for T,n0,n1,w0,w1 in [(25,32104,35131,1095,157),(60,19791,21178,1118,181),(75,7101,8152,1004,622)]:
 print('YUASA_2023',T,'cycle_ratio',round(n1/n0,4),'g_per_1000',round(1000*w0/n0,2),round(1000*w1/n1,2))
print('S3_SHORT_AUDIT_PASS; synthetic examples not physical calibration')
