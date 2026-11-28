"""Recalculate published plot-data error, not independent validation."""
from pathlib import Path
import xml.etree.ElementTree as ET,zipfile,statistics as st,math
r=Path(__file__).resolve().parents[1]/'sources/S3'
ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def load(n,skip):
 with zipfile.ZipFile(r/n) as z:
  rows=ET.fromstring(z.read('xl/worksheets/sheet1.xml')).findall('.//m:row',ns)[1:]
  return [tuple(float(c.findtext('m:v',namespaces=ns)) for c in row.findall('m:c',ns)[skip:]) for row in rows]
a=load('eval_30samples_lines_plot_data.xlsx',1);b=load('eval_30samples_scatter_plot_data.xlsx',0)
assert a==b and len(a)==30
print('DUPLICATE_PLOT_TABLES',len(a),'TRUE_RANGE',min(x[0] for x in a),max(x[0] for x in a))
for j in (1,2):
 e=[x[j]-x[0] for x in a]
 print('MODEL',j,'MAE',st.mean(map(abs,e)),'RMSE',math.sqrt(st.mean(v*v for v in e)),'BIAS',st.mean(e),'MAX_ABS',max(map(abs,e)))
print('MAE_REDUCTION',1-st.mean(abs(x[2]-x[0]) for x in a)/st.mean(abs(x[1]-x[0]) for x in a))
print('ROW_WINS',sum(abs(x[2]-x[0])<abs(x[1]-x[0]) for x in a))
print('PEUKERT_2006',64.3-67.6,100*(64.3/67.6-1),'HIGH_RATE_Q',44.2,'POST_REST_EXTRA_Q',64.3-44.2)
print('S3_METRICS_PASS')
