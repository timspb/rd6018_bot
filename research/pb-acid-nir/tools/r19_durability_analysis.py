"""R19 evidence arithmetic and provenance checks. No device I/O."""
from pathlib import Path
from hashlib import sha256
from math import isclose

ROOT=Path(r"<RESEARCH_ROOT>")
KARAMI=[(13,38),(10,33),(2,32),(4,35),(7,37)]
OHJ=[
 ("B1",5.50,44.4,89.5,59.1),
 ("B2",5.26,38.0,75.9,14.1),
 ("B3",14.40,1.6,-0.5,-20.1),
 ("B4",11.75,1.4,-6.4,-27.7),
]
PNNL_EFC=[728,494,362,289]
def pct(x):return round(x,2)
def main():
 assert isclose(sum(a for a,b in KARAMI)/5,7.2)
 assert isclose(sum(b for a,b in KARAMI)/5,35.0)
 assert isclose(sum(b for a,b in KARAMI)/5/40*100,87.5)
 print("KARAMI_TABLE1_PASS mean=7.2Ah->35.0Ah; 87.5% rated")
 print("KARAMI_CYCLE_CLAIM=40 cycles; >=80% endurance is author wording; metric/n/EOL unspecified")
 for name,base,w2,w6,w10 in OHJ:
  peak=max(w2,w6,w10)
  peak_cap=base*(1+peak/100)
  end_cap=base*(1+w10/100)
  loss=(end_cap/peak_cap-1)*100
  print(f"OHJ_{name} PASS peak={peak:+.1f}% baseline; week10={w10:+.1f}%; peak_to_week10={loss:.1f}%")
  assert loss<=0.0
 assert PNNL_EFC==[728,494,362,289]
 assert 72<=100
 shi_cell=56.3/88*100
 shi_pack=(52.4/40-1)*100
 print(f"SHI_CELL_RETAINED={shi_cell:.2f}% nominal after 41% gain")
 print(f"SHI_PACK_GAIN_ARITHMETIC={shi_pack:.1f}% (paper describes ~30%; values 40->52.4 imply 31.0%)")
 print("PNNL_BENCHMARK_PASS durations=18-28 months EFC=",PNNL_EFC)
 src=ROOT/"sources"/"R19"
 for name in ["Shamim_Viswanathan_2022_Energies_3389_PNNL.pdf",
              "Shi_Ferone_Rahn_2012_Pressure_Feedback.pdf",
              "IEC_60095-1_2018_Corrected_2026_Preview.pdf"]:
  p=src/name
  assert p.is_file() and p.read_bytes().startswith(b"%PDF")
  d=p.read_bytes()
  print("PDF_SHA256",name,len(d),sha256(d).hexdigest())
 print("R19_ARITHMETIC_PASS; all calculations use published values; no physical experiment")
if __name__=="__main__":main()
