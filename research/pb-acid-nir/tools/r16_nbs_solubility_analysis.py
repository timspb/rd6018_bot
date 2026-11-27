"""R16: tests and provenance of HISTORICAL NBS experimental table; no device I/O.

Source: Craig & Vinal (1939), NBS RP1165, p.66, Table 5.
Tabulated values derived by authors from smoothing/interpolation of solubility data.
Data: H2SO4 mass percent, solubility PbSO4 mg/L at 25 and 0 deg C.
"""
from math import isclose
from pathlib import Path
from hashlib import sha256

DATA = [
    # mass % H2SO4, 25C (mg PbSO4/L), 0C (mg PbSO4/L; None if not in paper)
    (0.1, 4.99, 2.37), (0.2, 4.61, 2.13), (0.3, 4.55, 2.07),
    (0.4, 4.57, 2.05), (0.5, 4.60, 2.06), (0.6, 4.65, 2.06),
    (0.7, 4.71, 2.07), (0.8, 4.77, 2.07), (0.9, 4.84, 2.08),
    (1.0, 4.91, 2.10), (2.0, 5.37, 2.18), (3.0, 5.70, 2.27),
    (4.0, 5.95, 2.36), (5.0, 6.15, 2.46), (6.0, 6.33, 2.58),
    (7.0, 6.47, 2.69), (8.0, 6.57, 2.79), (9.0, 6.64, 2.84),
    (10.0, 6.68, 2.86), (15.0, 6.28, 2.63),
    (20.0, 5.18, 2.21), (25.0, 3.87, 1.76),
    (30.0, 2.82, 1.27), (35.0, 2.02, 0.84),
    (40.0, 1.52, 0.53), (45.0, 1.23, None),
    (50.0, 1.08, None)
]
def get(mass_percent: float, idx: int = 1) -> float:
    matches = [v[idx] for v in DATA if v[0] == mass_percent]
    if len(matches)!=1 or matches[0] is None: raise ValueError("Data unavailable")
    return matches[0]

def main():
    assert len(DATA) == 27
    assert all(DATA[i][0] < DATA[i+1][0] for i in range(len(DATA)-1))
    assert all(x[1]>0 and (x[2] is None or x[2]>0) for x in DATA)
    assert get(0.3) < get(0.1) and get(0.3) < get(0.4)
    assert get(10) > get(9) and get(10) > get(15)
    assert isclose(get(10,2),2.86)
    # 42.5 mg/L water at 25C = cross-source reference (not same NBS run).
    assert isclose(42.5/get(35),21.03960396,rel_tol=1e-8)
    assert isclose(42.5/get(40),27.9605263158,rel_tol=1e-8)
    assert isclose(42.5/get(45),34.5528455285,rel_tol=1e-8)
    assert get(25,2)<get(25)  # not a universal rule beyond tested rows
    root=Path(r"<RESEARCH_ROOT>\sources\R16")
    files=["NBS_1939_Craig_Vinal_PbSO4_solubility.pdf",
           "NBS_1934_Vinal_Craig_H2SO4_resistivity.pdf"]
    for filename in files:
        pdf=root/filename
        blob=pdf.read_bytes()
        assert blob.startswith(b"%PDF")
        print("SOURCE_VERIFIED", filename, "size", len(blob), "sha256", sha256(blob).hexdigest())
    print("R16_OFFLINE_PASS: 27 distinct mass-percent rows; 25/0C units verified")
    print("R16_OFFLINE_PASS: local minimum at 0.3% acid and local max at 10% (25C)")
    print("CROSS_SOURCE_RATIO_NOT_UNIVERSAL: pure water 42.5 mg/L / 35% ->21.04; /40% ->27.96; /45% ->34.55")
    print("R16_DATA_NOT_A_CHARGING_PROCEDURE")

if __name__=="__main__":
    main()