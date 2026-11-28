from pathlib import Path
import urllib.request,hashlib,concurrent.futures
r=Path(__file__).resolve().parents[1]/'sources'/'S1'
r.mkdir(parents=True,exist_ok=True)
sources={
'Parnigotto_2022.pdf':'https://research.unipd.it/retrieve/77cf18a4-3dba-4e42-9914-8111bd895317/ChemElectroChem%20-%202022%20-%20Parnigotto%20-%20Water%20Loss%20Predictive%20Tests%20in%20Flooded%20Lead%E2%80%90Acid%20Batteries-1.pdf',
'Shiota_2001.pdf':'https://electronicsandbooks.com/edt/manual/Magazine/J/Journal%20of%20Power%20Sources/2001%20%28Vol%2095%29/No01-2%281-314%29/203-208.pdf',
'Hirai_2004.pdf':'https://www.jstage.jst.go.jp/article/jinstmet/68/2/68_2_35/_pdf/-char/en',
'Asserghine_2024.pdf':'https://zhaogroup.chbe.illinois.edu/publications/HZ425.pdf',
'Yuasa_2005.pdf':'https://www.gs-yuasa.com/jp/technology/technical_report/pdf/vol2_2/002_2_007.pdf',
'Charge_times_2024.pdf':'https://wrap.warwick.ac.uk/id/eprint/186228/7/batteries-10-00201-v2.pdf'}
def fetch(item):
 name,url=item
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Pb-Research academic archive'}),timeout=12) as f:b=f.read(20_000_001)
  assert b.startswith(b'%PDF') and len(b)<20_000_000
  (r/name).write_bytes(b);return (name,len(b),hashlib.sha256(b).hexdigest())
 except Exception as e:return (name,'NOT_ARCHIVED',str(e)[:100])
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:rows=list(ex.map(fetch,sources.items()))
for row in rows:print(*row)
(r/'SHA256SUMS.txt').write_text(''.join(f'{h}  {n}\n' for n,k,h in rows if isinstance(k,int)),encoding='utf-8')
