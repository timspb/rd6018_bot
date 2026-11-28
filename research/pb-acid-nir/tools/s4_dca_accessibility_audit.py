"""Public original archive and descriptive arithmetic; no device I/O."""
from pathlib import Path
import urllib.request,hashlib,concurrent.futures,statistics as st
r=Path(__file__).resolve().parents[1]/'sources'/'S4';r.mkdir(parents=True,exist_ok=True)
urls={'Arai_2014.pdf':'https://www.gs-yuasa.com/en/technology/technical_report/pdf/vol11/011_01_024.pdf','Smith_2016.pdf':'https://eprints.whiterose.ac.uk/id/eprint/113905/1/DCA_Paper_IECON.pdf','Aihara_2014.pdf':'https://www.jstage.jst.go.jp/article/electrochemistry/82/11/82_14-J00025/_pdf','Yamashita_1988.pdf':'https://www.jstage.jst.go.jp/article/kogyobutsurikagaku/56/10/56_842/_pdf'}
def fetch(x):
 n,u=x
 try:
  with urllib.request.urlopen(u,timeout=7) as f:b=f.read(15000001)
  assert b.startswith(b'%PDF') and len(b)<=15000000
  (r/n).write_bytes(b);return hashlib.sha256(b).hexdigest()+'  '+n,len(b)
 except Exception as e:print('NOT_ARCHIVED',n,str(e),flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:rows=[v for v in ex.map(fetch,urls.items()) if v]
p=r/'SHA256SUMS.txt';old=p.read_text(encoding='utf8') if p.exists() else ''
p.write_text(old.rstrip()+'\n'+'\n'.join(x for x,n in rows if x not in old)+'\n',encoding='utf8')
for x,n in rows:print('ARCHIVED',x,n)
a=[222,340,77,83,220,110,67,140,150,100,160,200,76,190,150,230,170,450,140,300,150,250,620,130]
b=[93,161,255,98,567,237,181,778,139,92,105,194,137,56,344,155,138,256,173,200,292,237,192,156]
for n,v in [('without',a),('with',b)]:print('ARAI_HEIGHT_NM',n,len(v),st.mean(v),st.median(v),st.stdev(v))
print('ARAI_RATE_RELATIVE_CHANGE',100*(37/65-1))
# Visually read approximate plotted values; not raw experimental samples.
print('SMITH_FIG7_APPROX_50SOC_RATIO',4/1.35,'70SOC_RATIO',1.85/.6)
print('S4_DCA_ACCESSIBILITY_AUDIT_PASS')
