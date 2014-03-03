#!/usr/bin/env python 


import os,sys
import os.path as op

import mtpy.core.edi as MTedi

from pylab import *



fn = sys.argv[1]

edi = MTedi.Edi()
edi.readfile(fn)


res_te=[]
res_tm=[]
phi_te=[]
phi_tm=[]
reserr_te=[]
reserr_tm=[]
phierr_te=[]
phierr_tm=[]

for r in edi.Z.resistivity:
	res_te.append(r[0,1])
	res_tm.append(r[1,0])

for p in edi.Z.phase:
    phi_te.append(p[0,1])
    phi_tm.append(p[1,0])

if np.mean(phi_te)>90 and np.mean(phi_tm)>90:
	phi_te = [i%90 for i in phi_te]
	phi_tm = [i%90 for i in phi_tm]

for r in edi.Z.resistivity_err:
	reserr_te.append(r[0,1])
	reserr_tm.append(r[1,0])
for p in edi.Z.phase_err:
    phierr_te.append(p[0,1])
    phierr_tm.append(p[1,0])

periods = 1./edi.freq


ax1 = subplot(211)
errorbar(periods,res_te,reserr_te, marker='s',c='b',fmt='x')
errorbar(periods,res_tm,reserr_tm, marker='s',c='r',fmt='x')
xscale('log')
yscale('log')
minval=min( min(res_te,res_tm))
maxval=max(max(res_te,res_tm))
ylim([minval/10,maxval*2])
ylabel('resistivity')
setp( ax1.get_xticklabels(), visible=False)
## share x only
ax2 = subplot(212, sharex=ax1)
errorbar(periods,phi_te,phierr_te,marker='s',c='b',fmt='x')
errorbar(periods,phi_tm,phierr_tm,marker='s',c='r',fmt='x')
ylabel('phase')
xlabel('period (in s)')

tight_layout()
show(block=True)
