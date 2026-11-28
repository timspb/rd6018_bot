"""R20-A05 synthetic identifiability counterexample; no hardware or measured data."""
import cmath, math
def z(f,grid,interface):
    return (3+grid+interface)+5/(1+2j*math.pi*f*.02)
def step(t,grid,interface):
    return 3+grid+interface+5*(1-math.exp(-t/.02))
for f in [0, .01,.1,1,10,100,1000,10000]:
    assert z(f,1,4)==z(f,4,1)
for t in [0,.001,.01,.1,1,10]:
    assert step(t,1,4)==step(t,4,1)
print('IDENTICAL_SPECTRA_AND_STEPS: different grid/interface contributions')
print('Kwiecien Table2 slope ratios:',.284/.112,.947/.399)
assert .284/.112>2.5 and .947/.399>2.3
print('R20_A05_PASS; synthetic structural nonidentifiability only')
