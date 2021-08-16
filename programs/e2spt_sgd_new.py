#!/usr/bin/env python
# Muyuan Chen 2021-08
from EMAN2 import *
import numpy as np
from e2spt_refine_new import gather_metadata

def main():
	
	usage=" "
	parser = EMArgumentParser(usage=usage,version=EMANVERSION)
	parser.add_argument("--path", type=str,help="path", default=None)
	parser.add_argument("--niter", type=int,help="iterations", default=50)
	parser.add_argument("--parallel", type=str,help="parallel", default="thread:12")
	parser.add_argument("--shrink", type=int,help="shrink", default=1)
	parser.add_argument("--batch", type=int,help="batch size", default=12)
	parser.add_argument("--ncls", type=int,help="number of class", default=1)
	parser.add_argument("--keep", type=float,help="keep fraction of good particles. will actually align more particles and use the number of particles specified by batch", default=.7)
	parser.add_argument("--learnrate", type=float,help="learning rate", default=.2)
	parser.add_argument("--res", type=float,help="resolution", default=50)
	parser.add_argument("--ref", type=str,help="reference", default=None)
	parser.add_argument("--classify",action="store_true",help="classify particles to the best class. there is the risk that some classes may end up with no particle. by default each class will include the best batch particles, and different classes can overlap.",default=False)

	#parser.add_argument("--sym", type=str,help="sym", default='c1')
	
	(options, args) = parser.parse_args()
	logid=E2init(sys.argv)
	ptcls=args[0]
	
	res=options.res
	lr=options.learnrate
	shrink=options.shrink
	batch=options.batch
	ncls=options.ncls
	
	if options.path==None: options.path=num_path_new("sptsgd_")
	path=options.path
	
	options.cmd=' '.join(sys.argv)
	fm=f"{path}/0_spt_params.json"
	js=js_open_dict(fm)
	js.update(vars(options))
	js.close()
	
	info2dname=f"{path}/particle_info_2d.lst"
	info3dname=f"{path}/particle_info_3d.lst"
	info2d, info3d = gather_metadata(ptcls)
	save_lst_params(info3d, info3dname)
	save_lst_params(info2d, info2dname)

	
	e=EMData(info3dname,0)
	if shrink>1:
		e.process_inplace("math.meanshrink",{"n":shrink})
	options.hdr=hdr=e.get_attr_dict()
	options.sz=sz=e["nx"]#//shrink
	options.pad=pad=EMData(info2dname,0,True)["nx"]//shrink

	npt=len(info3d)
	
	fnames=[f"{path}/output_all_cls{ic}.hdf" for ic in range(ncls)]
	for fname in fnames:
		if os.path.isfile(fname):
			os.remove(fname)
	
	thrd0s=[]
	if options.ref==None:
		for ic in range(ncls):
			idx=np.arange(npt)
			np.random.shuffle(idx)
			idx=np.sort(idx[:batch])
			tt=parsesym("c1")
			xfs=tt.gen_orientations("rand",{"n":batch,"phitoo":True})
			ali2d=[]
			for ii,xf in zip(idx,xfs):
				i2d=info3d[ii]["idx2d"]
				i2d=[info2d[i] for i in i2d]
				for i in i2d:
					d={"src":i["src"],"idx":i["idx"]}
					d["xform.projection"]=i["xform.projection"]*xf
					ali2d.append(d)
				
			thrd0=make_3d(ali2d, options)
			avg0=post_process(thrd0, options)
			avg0.write_image(f"{path}/output_cls{ic}.hdf")
			avg0.write_compressed(fnames[ic], -1, 12, nooutliers=True)
			thrd0s.append(thrd0)
		
	else:
		idx=np.arange(npt)
		np.random.shuffle(idx)
		idx=np.sort(idx[:batch])
		ali3d=[info3d[i] for i in idx]
		save_lst_params(ali3d, info3dname)
		
		launch_childprocess(f"e2spt_align_subtlt.py {path}/particle_info_3d.lst {options.ref} --path {path} --maxres {res} --parallel {options.parallel} --fromscratch --iter 0")
		ali2d=load_lst_params(f"{path}/aliptcls2d_00.lst")
		thrd0=make_3d(ali2d, options)
		thrd0s.append(thrd0)
		avg0=post_process(thrd0, options)
		avg0.write_image(f"{path}/output_cls0.hdf")
		avg0.write_compressed(fnames[0], -1, 12, nooutliers=True)
	
	for itr in range(options.niter):
		#print(itr)
		idx=np.arange(npt)
		np.random.shuffle(idx)
		nptcl=int(batch*ncls/options.keep)
		idx=np.sort(idx[:nptcl])
		ali3d=[info3d[i] for i in idx]
		save_lst_params(ali3d, info3dname)
		
		a3dout=[]
		a2dout=[]
		for ic in range(ncls):
			print(f"iter {itr}, class {ic}: ")
			launch_childprocess(f"e2spt_align_subtlt.py {path}/particle_info_3d.lst {path}/output_cls{ic}.hdf --path {path} --maxres {res} --parallel {options.parallel} --fromscratch --iter 0")
			
			a3dout.append(load_lst_params(f"{path}/aliptcls3d_00.lst"))
			a2dout.append(load_lst_params(f"{path}/aliptcls2d_00.lst"))
		
		
		score=[]
		for ali in a3dout:
			scr=[a["score"] for a in ali]
			score.append(scr)
		score=np.array(score)
		np.savetxt(f"{path}/score.txt", score.T)
		clsid=np.argmin(score, axis=0)
		for ic in range(ncls):
			if options.classify:
				scrid=np.where(clsid==ic)[0]
				print("  class {} - {} particles".format(ic, np.sum(clsid==ic)))
			else:
				scr=score[ic].copy()
				scrid=np.argsort(scr)[:batch]
			ali2d=[]
			for a in a2dout[ic]:
				if a["ptcl3d_id"] in scrid:
					ali2d.append(a)
					
			#print(len(ali2d))
									
			thrd1=make_3d(ali2d, options)
			thrd0=thrd0s[ic]
			
			out=thrd0*(1-lr)+thrd1*lr
			avg=post_process(out, options)
			avg.write_image(f"{path}/output_cls{ic}.hdf")
			avg.write_compressed(fnames[ic], -1, 12, nooutliers=True)

			thrd0s[ic]=out.copy()
			
	E2end(logid)
	

def make_3d(ali2d, options):
	#normvol=EMData(pad//2+1, pad, pad)
	pad=options.pad
	recon=Reconstructors.get("fourier", {"sym":'c1',"size":[pad,pad,pad], "mode":"trilinear"})
	recon.setup()
	for a in ali2d:
		e=EMData(a["src"],a["idx"])
		xf=Transform(a["xform.projection"])
		xf.set_trans(-xf.get_trans())
		
		if options.shrink>1:
			e.process_inplace("math.meanshrink",{"n":options.shrink})
			xf.set_trans(xf.get_trans()/options.shrink)
		
		ep=recon.preprocess_slice(e, xf)
		recon.insert_slice(ep,xf,1)

	threed=recon.finish(False)

	return threed


def post_process(threed, options):
	pad=options.pad
	sz=options.sz
	
	avg=threed.do_ift()
	avg.depad()
	avg.process_inplace("xform.phaseorigin.tocenter")
	avg=avg.get_clip(Region(pad//2-sz//2,pad//2-sz//2,pad//2-sz//2, sz,sz,sz), fill=0)
	avg.set_attr_dict(options.hdr)
	avg.process_inplace("filter.lowpass.gauss",{"cutoff_freq":1./options.res})
	avg.process_inplace("filter.highpass.gauss",{"cutoff_pixels":2})
	
	if options.shrink>1:
		avg.process_inplace("math.fft.resample",{"n":1/options.shrink})
	avg.process_inplace("normalize.edgemean")
	avg.process_inplace("mask.soft",{"outer_radius":-10,"width":10})
	
	return avg
	
	
if __name__ == '__main__':
	main()
	
