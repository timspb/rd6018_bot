"""Archive only open-access, explicitly enumerated R14 research PDFs."""
from pathlib import Path
import hashlib
from urllib.request import Request, urlopen

OUT = Path(r"<RESEARCH_ROOT>\sources\R14")
OUT.mkdir(parents=True, exist_ok=True)
DOCUMENTS = [
    ("Bauknecht_2023_DCA_EIS_EFB.pdf",
     "https://depositonce.tu-berlin.de/bitstreams/f6067135-a024-4ab8-86fd-a5d75fd665ac/download"),
    ("JACI_2023_EFB_AGM_stratification.pdf",
     "https://www.jaci.or.jp/english/gscn/GSCpdfs/gsc_guide_no06.pdf"),
]
for name, url in DOCUMENTS:
    dest = OUT / name
    if dest.exists() and dest.read_bytes().startswith(b"%PDF"):
        print("PRESENT", name, dest.stat().st_size)
        continue
    try:
        with urlopen(Request(url, headers={"User-Agent": "Pb-Research/1.0 literature archive"}), timeout=18) as f:
            data = f.read(15_000_001)
        if not data.startswith(b"%PDF") or len(data) > 15_000_000:
            print("NOT_ARCHIVED", name, "unexpected format or size", len(data))
            continue
        dest.write_bytes(data)
        print("ARCHIVED", name, len(data), hashlib.sha256(data).hexdigest(), flush=True)
    except Exception as ex:
        print("ARCHIVE_FAILED", name, type(ex).__name__, flush=True)