"""Reproduce descriptive arithmetic of published Table A1; no equipment access."""
rows={'1-C':(.298,.190,.330,.412),'1+C':(.401,.226,.398,.474),'2+C':(.543,.388,.632,.710),'3+C':(.525,.437,.770,.800)}
for k,(b,f,m,s) in rows.items():
 print(k,'small/battery',round(s/b,4),'small/full-cell',round(s/f,4))
assert rows['2+C'][0]>rows['3+C'][0] and rows['2+C'][3]<rows['3+C'][3]
assert abs((1-.3)*100-70)<1e-9
print('S1_TRANSFER_MATH_PASS: descriptive, not independent validation')
