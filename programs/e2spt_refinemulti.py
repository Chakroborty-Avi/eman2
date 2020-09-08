#!/usr/bin/env python
# Muyuan Chen 2017-03
# Steve Ludtke 2020-09 adapted from e2spt_refine
from builtins import range
from EMAN2 import *
import numpy as np
from EMAN2_utils import *

def main():
	
	usage="""prog <particle stack> --ref <reference> [options]
	Iterative subtomogram refinement.  
	"""
	parser = EMArgumentParser(usage=usage,version=EMANVERSION)
	parser.add_pos_argument(name="particles",help="Specify particles to use to generate an initial model.", default="", guitype='filebox', browser="EMSetsTable(withmodal=True,multiselect=False)", row=0, col=0,rowspan=1, colspan=3, mode="model")
	parser.add_argument("--ref", action="append", help="""3D reference for iterative alignment/averaging. <name> or <name>,#. For multiple references use this option multiple times. The first reference will be used for alignment.""", guitype='filebox', browser="EMBrowserWidget(withmodal=True,multiselect=False)", row=1, col=0,rowspan=1, colspan=3, mode="model")

	parser.add_header(name="orblock1", help='Just a visual separation', title="Options", row=2, col=1, rowspan=1, colspan=1, mode="model")

	parser.add_argument("--mask", type=str,help="Mask file to be applied to initial model", default="", guitype='filebox', browser="EMBrowserWidget(withmodal=True,multiselect=False)", row=3, col=0,rowspan=1, colspan=3, mode="model")
	parser.add_argument("--maskalign", type=str,help="Mask file applied to 3D alignment reference in each iteration. Not applied to the average, which will follow normal masking routine.", default="", guitype='filebox', browser="EMBrowserWidget(withmodal=True,multiselect=False)", row=4, col=0,rowspan=1, colspan=3, mode="model")
	parser.add_argument("--maskref", type=str,help="Mask file applied to 3D classification references in each iteration. Not applied to the average.", default="", guitype='filebox', browser="EMBrowserWidget(withmodal=True,multiselect=False)", row=4, col=0,rowspan=1, colspan=3, mode="model")

	parser.add_argument("--niter", type=int,help="Number of iterations", default=5, guitype='intbox',row=5, col=0,rowspan=1, colspan=1, mode="model")
	parser.add_argument("--sym", type=str,help="symmetry", default="c1", guitype='strbox',row=5, col=1,rowspan=1, colspan=1, mode="model")
	
	parser.add_argument("--setsf", type=str,help="structure factor", default=None, guitype='filebox', browser="EMBrowserWidget(withmodal=True,multiselect=False)", row=7, col=0,rowspan=1, colspan=3, mode="model")

	parser.add_argument("--maxtilt",type=float,help="Explicitly zeroes data beyond specified tilt angle. Assumes tilt axis exactly on Y and zero tilt in X-Y plane. Default 90 (no limit).",default=90.0, guitype='floatbox',row=8, col=2,rowspan=1, colspan=1, mode="model")

	parser.add_argument("--restarget",type=float,help="Filters each map at the end of each iteration to this resolution (in A) since FSC isn't available",default=-1.0)

	parser.add_argument("--path", type=str,help="Specify name of refinement folder. Default is spt_XX.", default=None)#, guitype='strbox', row=10, col=0,rowspan=1, colspan=3, mode="model")
	parser.add_argument("--maxang",type=float,help="maximum anglular difference in refine mode.",default=30)
	parser.add_argument("--maxshift",type=float,help="maximum shift in pixel.",default=-1)

	parser.add_argument("--ppid", type=int, help="Set the PID of the parent process, used for cross platform PPID",default=-2)
	parser.add_argument("--threads", type=int,help="threads", default=12, guitype='intbox',row=9, col=0,rowspan=1, colspan=1, mode="model")
	parser.add_argument("--parallel", type=str,help="Thread/mpi parallelism to use", default="")
	parser.add_argument("--transonly",action="store_true",help="translational alignment only",default=False)
	parser.add_argument("--refine",action="store_true",help="local refinement from xform in header.",default=False)
	parser.add_argument("--randphi",action="store_true",help="randomize phi for refine search",default=False)
	parser.add_argument("--rand180",action="store_true",help="include 180 degree rotation for refine search",default=False)
	parser.add_argument("--scipy",action="store_true",help="test scipy refinement",default=False)
	
	#parser.add_argument("--masktight", type=str,help="Mask_tight file", default="")

	(options, args) = parser.parse_args()
	logid=E2init(sys.argv)
	ptcls=args[0]
	if options.restarget<=0: 
		print("Error: --restarget is required")
		sys.exit(1)
	refs=[i.split(",") for i in options.ref]
	refss=" ".join(options.ref)
	# refs[n][0] is the filename, refs[n][1] is the image number
	for i in range(len(refs)):
		if len(refs[i])==1: refs[i].append(0)
		else: refs[i][1]=int(refs[i][1])
	ref=refs[0][0]
	refn=refs[0][1]

	curres=20
	startitr=1
		
	if options.path==None: options.path = make_path("spt") 
	if options.parallel=="":
		options.parallel="thread:{}".format(options.threads)
	
	msk=options.mask
	if len(msk)>0:
		if os.path.isfile(msk):
			msk=" --automask3d mask.fromfile:filename={}".format(msk)
		else:
			msk=" --automask3d {}".format(msk)

	#### make a list file if the particles are not in a lst
	if ptcls.endswith(".json"):
		jstmp=js_open_dict(ptcls)
		ky=jstmp.keys()[0]
		pt,ii=eval(ky)
		ep=EMData(pt, ii)
	elif ptcls.endswith(".lst"):
		ep=EMData(ptcls,0)
	else:
		ptcllst="{}/input_ptcls.lst".format(options.path)
		run("e2proclst.py {} --create {}".format(ptcls, ptcllst))
		ptcls=ptcllst
		ep=EMData(ptcls,0)

	options.input_ptcls=ptcls
	options.input_ref=refs
	options.cmd=' '.join(sys.argv)

	# This seems a bit poorly concieved?
	for i in range(10):
		fm="{}/{}_spt_params.json".format(options.path, i)
		if not os.path.isfile(fm):
			js=js_open_dict(fm)
			js.update(vars(options))
			js.close()
			break
	
	# Initial seed
	er=EMData(refs[0][0],refs[0][1],True)
	if er["apix_x"]==1.0 : print("Warning, A/pix exactly 1.0. You may wish to double-check that this is correct!")
	if abs(1-ep["apix_x"]/er["apix_x"])>0.01 or ep["nx"]!=er["nx"]:
		print("apix mismatch {:.2f} vs {:.2f}".format(ep["apix_x"], er["apix_x"]))
		rs=er["apix_x"]/ep["apix_x"]
		if rs>1.:
			run("e2proc3d.py {} {}/model_input.hdf --clip {} --scale {} --process mask.soft:outer_radius=-1 --first {} --last {}".format(refs[0][0], options.path, ep["nx"], rs,refs[0][1],refs[0][1]))
		else:
			run("e2proc3d.py {} {}/model_input.hdf --scale {} --clip {} --process mask.soft:outer_radius=-1 --first {} --last {}".format(refs[0][0], options.path, rs, ep["nx"],refs[0][1],refs[0][1]))
	else:	
			run("e2proc3d.py {} {}/model_input.hdf --process mask.soft:outer_radius=-1 --first {} --last {}".format(refs[0][0], options.path, refs[0][1],refs[0][1]))
		
	
	for itr in range(startitr,options.niter+startitr):

		# the alignment ref may be masked using a different file, or just copied
		ar=EMData(ref,refn)
		if (len(options.maskalign)>0):
			m=EMData(options.maskalign,0)
			ar.mult(m)
		ar.write_image(f"{options.path}/alignref.hdf",0)
		
		#### generate alignment command first
		if options.refine:
			gd+=" --refine --maxang {:.1f}".format(options.maxang)
			if options.randphi:
				gd+=" --randphi"
			if options.rand180:
				gd+=" --rand180"
			if itr>startitr:
				ptcls=os.path.join(options.path, "particle_parms_{:02d}.json".format(itr-1))

		if options.transonly: gd+=" --transonly"

		gd=""
		if options.maxshift>0:
			gd+=" --maxshift {:.1f}".format(options.maxshift)
		if options.scipy:
			gd+=" --scipy"

		cmd="e2spt_align.py {} {}/alignref.hdf --parallel {} --path {} --iter {} --sym {} --maxres {} {}".format(ptcls, options.path,  options.parallel, options.path, itr, options.sym, options.restarget, gd)
		
		ret=run(cmd)
		
		
		s=""
		if options.maxtilt<90.:
			s+=" --maxtilt {:.1f}".format(options.maxtilt)
		
		run(f"e2spt_average_multi.py {refss} --parallel {options.parallel} --path {options.path} --sym {options.sym} {s} --iter {itr} --mask {options.maskref}")
		

		ref=os.path.join(options.path, "threed_{:02d}_00.hdf".format(itr))
		refn=0
		refss=" ".join([f"{options.path}/threed_{itr:02d}_{k:02d}.hdf" for k in range(len(refs))]) 

	E2end(logid)
	
def run(cmd):
	print(cmd)
	ret=launch_childprocess(cmd)
	return ret
	
	
if __name__ == '__main__':
	main()

