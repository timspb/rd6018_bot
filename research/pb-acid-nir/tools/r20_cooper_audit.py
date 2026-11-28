"""Offline numerical check of published Cooper 2002 Tables 4.2/4.3; high-rate discharge time, NOT capacity."""
data = [('A',654.8,717.2,598.6,591.8),('B',883,1158.2,1053,1157.8),('C',222.6,315,251.6,382.6),('D',353.2,362.4,351.4,373.4),('E',322.4,284.2,306.8,260.2),('F',.2,.2,.2,.2)]
def pct(a,b): return 100*(b-a)/a
d=[]
for name,a,b,c,e in data:
    x,y=pct(a,b),pct(c,e)
    d.append(y-x)
    print(f'{name}: ordinary={x:.4f}% pulse={y:.4f}% contrast={y-x:+.4f}pp')
assert sum(v>1e-9 for v in d)==2
assert sum(v<-1e-9 for v in d)==3
assert sum(abs(v)<=1e-9 for v in d)==1
assert sum(b>a for _,a,b,c,e in data)==4
assert abs(d[2]-10.56)<.02
assert abs(d[3]-3.66)<.02
print('R20_A03_COOPER_PASS; descriptive only, no C20 or causal population estimate')
