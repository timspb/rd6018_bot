"""Archive known public/open research/reference PDFs; check signature and hashes."""
from pathlib import Path
from urllib.request import Request, urlopen
from hashlib import sha256

OUT = Path(r"<RESEARCH_ROOT>\sources\R15")
OUT.mkdir(parents=True, exist_ok=True)
SOURCES = (
    ("Batteries_2024_Heat_Effects.pdf",
     "https://artefacts-discovery.researcher.life/full_text/DA-2/1a/1a46598ab6683366b1f3913a58597d99/full_text/367b1d1a2bb157353339e47e810535f3.pdf"),
    ("OSTI_East_Penn_UltraBattery_2015.pdf",
     "https://www.osti.gov/servlets/purl/1349503"),
    ("EnerSys_PowerSafe_SBS_XC_2023.pdf",
     "https://www.enersys.com/4a626d/globalassets/documents/product-documentation/powersafe/sbs-xc-plus/emea/en-og-emea-ogre-powersafe-bsxc-0723.pdf"),
    ("EnerSys_PowerSafe_SBS_EON_2020.pdf",
     "https://www.enersys.com/493bb4/globalassets/documents/product-documentation/powersafe/sbs-eon/emea/en-sbs-eon-iom-009--11.2020.pdf"),
)
for name, uri in SOURCES:
    dest=OUT/name
    if dest.exists() and dest.stat().st_size>5000 and dest.open("rb").read(5).startswith(b"%PDF"):
        print("EXISTING",name,"sha256="+sha256(dest.read_bytes()).hexdigest())
        continue
    try:
        with urlopen(Request(uri,headers={"User-Agent":"Mozilla/5.0 (local academic reference archiving)"}), timeout=16) as conn:
            data=conn.read(16000001)
        if len(data)>16000000 or not data.startswith(b"%PDF"):
            print("REJECT_NONPDF",name,"size="+str(len(data)))
            continue
        dest.write_bytes(data)
        print("ARCHIVED",name,"bytes="+str(len(data)),"sha256="+sha256(data).hexdigest())
    except Exception as e:
        print("ARCHIVE_UNAVAILABLE",name,type(e).__name__)