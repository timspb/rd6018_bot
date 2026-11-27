"""R17: reconstruct reported experimental comparisons; NOT a battery charger.

Provenance of data:
1) Bozkaya et al. Energy Technol 2022 DOI 10.1002/ente.202101051,
   full original PDF p3, laboratory 2V 2.5Ah NAM-limited cells, all 2wt% carbon.
2) Xie et al. Heliyon 2024 DOI 10.1016/j.heliyon.2024.e31339,
   indexed abstract/full-text search, laboratory HRPSoC microcycles at 50% SoC/2C.
3) Molecules 2023 28 5618 DOI 10.3390/molecules28145618,
   indexed results, laboratory HRPSoC microcycles.
"""
from math import isclose
from pathlib import Path
from hashlib import sha256

# PSoC microcycles are NOT complete 100% DoD charge/discharge cycles.
CF_MICROCYCLES = {
    "blank":1267, "AC_1pct":1521, "CF_0_5pct":1884,
    "CF_1pct":3642, "CF_1_5pct":2077, "CF_2pct":1803
}
NCC_MICROCYCLES = {"blank":809,"AC":1834,"NCC":4324}
# Bozkaya: external carbon specific surface m2/g and CA current normalized by C20,
# intentionally includes only directly paired, reported data points from p3 text.
BOZKAYA_PAIR = {
    "C1":(7.1, 0.21),
    "C4":(92.1, 0.58),
    "C5":(159.3, None)  # article states plateau, does not claim exact C5 value
}

def show():
    assert len(CF_MICROCYCLES)==6
    assert max(CF_MICROCYCLES,key=CF_MICROCYCLES.get)=="CF_1pct"
    assert isclose(CF_MICROCYCLES["CF_1pct"]/CF_MICROCYCLES["blank"],2.87450670876,rel_tol=1e-10)
    assert isclose(CF_MICROCYCLES["CF_1pct"]/CF_MICROCYCLES["AC_1pct"],2.39447731755,rel_tol=1e-10)
    assert NCC_MICROCYCLES["NCC"] / NCC_MICROCYCLES["blank"] > 5.3
    assert NCC_MICROCYCLES["NCC"] / NCC_MICROCYCLES["AC"] > 2.3
    assert isclose(BOZKAYA_PAIR["C4"][1]/BOZKAYA_PAIR["C1"][1],0.58/0.21)
    assert BOZKAYA_PAIR["C5"][1] is None, "Do not invent unavailable numerical results"
    original=Path(r"<RESEARCH_ROOT>\sources\R17")
    docs={
      "Bozkaya_2022_DCA_Carbon_Screening.pdf":"e09e9c2149ecf6b2326f341e476db77fd52ce3a8fb9bd5188aeff638d98f082b",
      "Lach_2019_Review_Applications_of_Carbon.pdf":"89b51956fde7a76d3931c2c793550be853aae3b8109f009fafe0c6eb96d154f3",
    }
    for file,expected in docs.items():
        data=(original/file).read_bytes()
        assert data.startswith(b"%PDF") and sha256(data).hexdigest()==expected
        print("HASH_PASS",file,len(data))
    print("CF_HRPSoC_LAB_ONLY: 1pct carbon foam",CF_MICROCYCLES["CF_1pct"],
          "blank",CF_MICROCYCLES["blank"],
          "ratio",round(CF_MICROCYCLES["CF_1pct"]/CF_MICROCYCLES["blank"],3))
    print("NCC_HRPSoC_LAB_ONLY: NCC",NCC_MICROCYCLES["NCC"],
          "blank",NCC_MICROCYCLES["blank"],
          "ratio",round(NCC_MICROCYCLES["NCC"]/NCC_MICROCYCLES["blank"],3))
    print("BOZKAYA_SHORT_TERM: surface",BOZKAYA_PAIR["C1"][0],"->",BOZKAYA_PAIR["C4"][0],
          "CA",BOZKAYA_PAIR["C1"][1],"->",BOZKAYA_PAIR["C4"][1],
          "ratio",round(BOZKAYA_PAIR["C4"][1]/BOZKAYA_PAIR["C1"][1],3))
    print("R17_OFFLINE_PASS: source numbers and archive hashes; no physical experiments")

if __name__=="__main__":
    show()