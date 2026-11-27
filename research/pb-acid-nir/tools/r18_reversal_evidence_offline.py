"""R18: offline literature arithmetic and observability checks. No device I/O.

Data from Karami et al., Energy Conversion and Management 50 (2009) Table 1;
not a reconditioning method, not an electrochemical simulation or safety gate.
"""
from math import isclose

KARAMI_PAIRS_AH=[(13,38),(10,33),(2,32),(4,35),(7,37)]
NOMINAL_AH=40
def main():
    assert len(KARAMI_PAIRS_AH)==5
    assert all(0<=a<=NOMINAL_AH and 0<=b<=NOMINAL_AH for a,b in KARAMI_PAIRS_AH)
    initial=[a for a,b in KARAMI_PAIRS_AH]
    final=[b for a,b in KARAMI_PAIRS_AH]
    percentage=[100*v/NOMINAL_AH for v in final]
    assert isclose(sum(initial)/5,7.2)
    assert isclose(sum(final)/5,35)
    assert isclose(sum(percentage)/5,87.5)
    assert isclose(sum(final)/sum(initial),175/36)
    # Data quality check: paper text "all initial <25%" is contradicted.
    contradict=[(i+1,a,100*a/NOMINAL_AH) for i,a in enumerate(initial)
                if not 100*a/NOMINAL_AH < 25]
    assert len(contradict)==2
    assert contradict[0][2]==32.5 and contradict[1][2]==25
    # Terminal voltage cannot determine all 6 cell voltages: two
    # mathematical vectors have the same sum but different internal states.
    case1=[1.75]*6
    case2=[2.15]*5+[-0.25]
    assert isclose(sum(case1),10.5)
    assert isclose(sum(case2),10.5)
    assert all(v>0 for v in case1)
    assert any(v<0 for v in case2)
    print("R18_KARAMI_TABLE1_PASS 5 batteries, mean initial 7.2Ah, "
          "mean final 35.0Ah, mean Cfinal/Cnominal 87.5%")
    print("R18_INTERNAL_INCONSISTENCY_PRESENT baseline <25% contradicted by",contradict)
    print("R18_OBSERVABILITY_PASS synthetic Utotal=10.5V can hide a negative Ucell")
    print("No real battery experiments, no advice to reverse-charge.")
if __name__=="__main__":
    main()