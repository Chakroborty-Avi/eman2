#!/usr/bin/env python
# Muyuan Chen 2020-05
from EMAN2 import *
import numpy as np

def main():
	
	usage=""" New single particle refinement routine. Still under construction. For simple usage,
	e2spa_refine.py --ptcl <particle list file> --ref <reference map> --res <inital resoution>
	"""
	parser = EMArgumentParser(usage=usage,version=EMANVERSION)
	parser.add_argument("--ptcl", type=str,help="particle input", default="")
	parser.add_argument("--ref", type=str,help="reference", default="")
	parser.add_argument("--path", type=str,help="path. default is r3d_00", default="r3d_00")
	parser.add_argument("--parallel", type=str,help="", default="thread:1")
	parser.add_argument("--sym", type=str,help="sym", default="c1")
	parser.add_argument("--res", type=float,help="The resolution that reference map is lowpass filtered to (with phase randomization) at the begining of the refinement. ", default=10)
	parser.add_argument("--keep", type=float,help="keep", default=.9)
	parser.add_argument("--startiter", type=int,help="iter", default=0)
	parser.add_argument("--niter", type=int,help="iter", default=10)
	parser.add_argument("--setsf", type=str,help="structure factor", default="strucfac.txt")
	parser.add_argument("--slow", action="store_true", default=False ,help="slow but finer search. not used yet")

	(options, args) = parser.parse_args()
	logid=E2init(sys.argv)
	
	res=options.res
	sym=options.sym
		
	tophat=""
	npt=EMUtil.get_image_count(options.ptcl)
	
	if options.slow:
		slow=" --slow"
	else:
		slow=""
	
	if options.startiter==0:
		if not os.path.isdir(options.path):
			os.mkdir(options.path)
		
		r=1/res
		for i,eo in enumerate(["even","odd"]):
			run("e2proclst.py {} --create {}/ptcls_00_{}.lst --range {},{},2".format(options.ptcl, options.path, eo, i, npt))
			run("e2proc3d.py {} {}/threed_00_{}.hdf --process filter.lowpass.gauss:cutoff_freq={:.4f} --process filter.lowpass.randomphase:cutoff_freq={:.4f}".format(options.ref, options.path, eo, r,r))
	
	
	for i in range(options.startiter, options.startiter+options.niter):
		
		for eo in ["even","odd"]:
			run("e2spa_align.py --ptclin {pt}/ptcls_{i0:02d}_{eo}.lst --ptclout {pt}/ptcls_{i1:02d}_{eo}.lst --ref {pt}/threed_{i0:02d}_{eo}.hdf --parallel {par} --sym {s} --maxres {rs:.2f} {sl}".format(pt=options.path, i0=i, i1=i+1, rs=res, eo=eo, s=sym, par=options.parallel,sl=slow))
			run("e2spa_make3d.py --input {pt}/ptcls_{i1:02d}_{eo}.lst --output {pt}/threed_{i1:02d}_{eo}.hdf --keep {kp} --sym {s} --parallel {par}".format(pt=options.path, i1=i+1, eo=eo, s=sym, par=options.parallel, kp=options.keep))

		if i==options.startiter:
			res/=2
			
		if i>0:
			tophat=" --tophat local"
		run("e2refine_postprocess.py --even {pt}/threed_{i1:02d}_even.hdf --sym {s} --setsf {sf} --restarget {rs:.1f} {tp}".format(pt=options.path, i1=i+1, s=sym, sf=options.setsf, rs=res*.8, tp=tophat))
		
		fsc=np.loadtxt("{}/fsc_masked_{:02d}.txt".format(options.path, i+1))
		fi=fsc[:,1]<0.2
		res=1./fsc[fi, 0][0]
		res*=.8

	E2end(logid)
	
def run(cmd):
	print(cmd)
	launch_childprocess(cmd)
	
	
if __name__ == '__main__':
	main()
	
