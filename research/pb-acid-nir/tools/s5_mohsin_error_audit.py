"""Recalculate published Mohsin et al. 2022 Table III. No instrument I/O."""
from statistics import mean
Q=[18.28,17.472,14.84,14.24,4.2,2.2,4.2,16.64]
P=[[17.85,18.12,12.79,15.41,3.71,1.17,1.95,16.06],
[18.37,18.14,13.35,14.91,4.82,1.06,3.02,15.86],
[18.53,17.77,13.93,13.70,4.67,.95,2.44,16.44],
[18.64,17.64,14.61,14.65,5.34,1,4.31,16.95],
[18.16,17.56,14.56,14.58,6.2,1.12,4.96,17.11],
[17.19,16.92,15.16,14.67,6.53,1.48,5.70,17.29],
[16.73,15.52,14.75,14.29,7.49,1.82,6.23,17.41]]
PUBLISHED=[1.61,.42,3.1,1.65,6.1,4.42,.52,.41]
def main():
    metrics=[]
    for i,q in enumerate(Q):
        d=[r[i]-q for r in P]
        mae=mean(map(abs,d));bias=mean(d);mape=100*mae/q;pp=100*mae/22;biaspp=100*abs(bias)/22
        assert abs(biaspp-PUBLISHED[i])<.04
        metrics.append((mae,mape,pp))
        print(i+1,'MAE',round(mae,4),'MAPE',round(mape,3),'MAE nominal pp',round(pp,3),'abs bias nominal pp',round(biaspp,3))
    macro=[mean(r[i] for r in metrics) for i in range(3)]
    assert abs(macro[0]-.852392857142857)<1e-9
    print('MACRO MAE Ah, MAPE %, MAE nominal pp',macro)
    print('56 repeated SOC configurations, 8 aged specimens; no independent validation. TABLE_RECALC_PASS')
if __name__=='__main__':main()
