"""Public dataset provenance and schema inspection; no hardware."""
from pathlib import Path
import urllib.request,hashlib,zipfile,xml.etree.ElementTree as ET,csv,concurrent.futures
r=Path(__file__).resolve().parents[1]/'sources'/'S3';r.mkdir(parents=True,exist_ok=True)
items=[('cycle_sweep_data_20251120-093336.csv','5ed4a6ca47c8bfa0a56e38226fd945ab'),('dod_sweep_data_20251120-093336.csv','fc8be7e5a33d8f32698f8811418f5a95'),('temperature_sweep_data_20251120-093336.csv','d5c377c8656e0179675964e3c7c61130'),('eval_30samples_lines_plot_data.xlsx','6e3ac753566647fe2076e66ca884f65c'),('eval_30samples_scatter_plot_data.xlsx','5db9b48d26ab4682ed044678444041c4')]
def get(x):
 n,h=x
 try:
  with urllib.request.urlopen('https://zenodo.org/records/21996450/files/'+n+'?download=1',timeout=8) as f:b=f.read(100000)
  assert hashlib.md5(b).hexdigest()==h,'MD5 mismatch'
  (r/n).write_bytes(b);return n,hashlib.sha256(b).hexdigest()
 except Exception as e:print('NOT_ARCHIVED',n,str(e),flush=True);return None
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:rows=[x for x in ex.map(get,items) if x]
p=r/'SHA256SUMS.txt';old=p.read_text(encoding='utf8') if p.exists() else ''
p.write_text(old.rstrip()+'\n'+'\n'.join(h+'  '+n for n,h in rows if h+'  '+n not in old)+'\n',encoding='utf8')
ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
for n,h in rows:
 print('ARCHIVED',n,h)
 if n.endswith('.csv'):print((r/n).read_text(encoding='utf-8-sig'))
 else:
  with zipfile.ZipFile(r/n) as z:
   strings=[]
   if 'xl/sharedStrings.xml' in z.namelist():
    strings=[''.join(t.text or '' for t in si.findall('.//m:t',ns)) for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',ns)]
   for name in z.namelist():
    if name.startswith('xl/worksheets/sheet') and name.endswith('.xml'):
     rs=[]
     for row in ET.fromstring(z.read(name)).findall('.//m:row',ns):
      vals=[]
      for c in row.findall('m:c',ns):
       v=c.findtext('m:v',default='',namespaces=ns)
       if c.get('t')=='s':v=strings[int(v)]
       if c.get('t')=='inlineStr':v=''.join(t.text or '' for t in c.findall('.//m:t',ns))
       vals.append(v)
      rs.append(vals)
     print('SHEET',name,'rows',len(rs),'first',rs[:4],'last',rs[-2:])
print('S3_SOH_SCHEMA_COMPLETE',len(rows),'of',len(items))
