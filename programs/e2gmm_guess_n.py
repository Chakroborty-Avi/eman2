#!/usr/bin/env python
# Muyuan Chen 2023-03
from EMAN2 import *
from EMAN2_utils import *
from scipy.spatial import KDTree
import numpy as np
from sklearn.cluster import KMeans

def main():

	usage="""
	Guess the number of Gaussian needed to represent a given volume. 
	e2gmm_guess_n.py threed_xx.hdf --thr 3 --maxres 3
	"""
	parser = EMArgumentParser(usage=usage,version=EMANVERSION)
	parser.add_argument("--thr", type=float,help="threshold", default=-1)
	parser.add_argument("--maxres", type=float,help="resolution", default=3)
	parser.add_argument("--minres", type=float,help="resolution", default=100)
	parser.add_argument("--startn", type=int,help="", default=1000)
	parser.add_argument("--maxn", type=int,help="", default=20000)
	parser.add_argument("--evenodd", action="store_true", default=False ,help="segment on combined map and refine on even/odd")

	(options, args) = parser.parse_args()
	
	logid=E2init(sys.argv)
	fname=args[0]
		
	e=EMData(fname)
	if options.thr<0:
		options.thr=e["sigma"]*4
	img=e.numpy().copy()
	pts=np.array(np.where(img>options.thr)).T
	
	val=img[pts[:,0], pts[:,1], pts[:,2]]
	#pts[:,1:]=e["nx"]-pts[:,1:]
	pts=pts[:,::-1]
	pts=pts*e["apix_x"]
	pts=pts[np.argsort(-val)]
	
	tree=KDTree(pts)
	d=tree.query(pts, k=2)[0][:,1]
	dm=np.sort(d)[len(d)//2]
	print(np.sort(d))
	print(len(pts), np.mean(d), np.median(d))
	#print("{:<5} {:.4f}".format(len(pts), dm))
	res=max(options.maxres/2., 1.3) ## shouldn't have atoms that close even for atomic model
	
	tokeep=np.ones(len(pts), dtype=bool)
	for i in range(len(pts)):
		if tokeep[i]:
			k=tree.query_ball_point(pts[i], res)
			tokeep[k]=False
			tokeep[i]=True
			
	print(np.sum(tokeep))
	
	options.maxn=min(options.maxn, len(pts))
	nrng=np.arange(options.startn, options.maxn+1, 1000)
	
	pdbname=fname[:-4]+"_seg.pdb"
	gmmname=fname[:-4]+"_gmm.txt"
	fscname=fname[:-4]+"_fsc.txt"
	avgname=fname[:-4]+"_gmm.hdf"
	
	print("N:    dist")
	for n in nrng:
		p0=pts.copy()
		np.random.shuffle(p0)
		p0=p0[:n]
		#p0+=np.random.randn(len(p0),3)*.1
		km=KMeans(n,init=p0, n_init=1,max_iter=100)
		km.fit(pts)
		p=km.cluster_centers_
		
		tree=KDTree(p)
		d=tree.query(p, k=2)[0][:,1]
		dm=np.sort(d)[len(d)//3]
		#print(np.sort(d))
		print("{:<5} {:.4f}".format(n, dm))
		numpy2pdb(p, pdbname)
		if dm<res:
			print(f"stop. using N={n}")
			break
			
	if options.evenodd:
		for eo in ["even", "odd"]:
			run(f"e2project3d.py {fname[:-4]}_{eo}.hdf --outfile {fname[:-4]}_tmp_projection.hdf --orientgen=eman:delta=4 --parallel=thread:16")
			run(f"e2gmm_refine_new.py --ptclsin {fname[:-4]}_tmp_projection.hdf --model {pdbname} --maxres {options.maxres} --minres {options.minres} --modelout {gmmname[:-4]}_{eo}.txt --niter 40 --trainmodel --evalmodel {fname[:-4]}_tmp_model_projections.hdf --learnrate 1e-5")
			run(f"e2spa_make3d.py --input {fname[:-4]}_tmp_model_projections.hdf --output {avgname[:-4]}_{eo}.hdf --thread 32")
			run(f"e2proc3d.py {avgname[:-4]}_{eo}.hdf {avgname[:-4]}_{eo}.hdf --process mask.soft:outer_radius=-16 --matchto {fname[:-4]}_{eo}.hdf")
			run(f"e2proc3d.py {avgname[:-4]}_{eo}.hdf {fscname[:-4]}_{eo}.txt --calcfsc {fname[:-4]}_{eo}.hdf")
			
			os.remove(f"{fname[:-4]}_tmp_projection.hdf")
			os.remove(f"{fname[:-4]}_tmp_model_projections.hdf")
			
		print("final pdb model: "+ pdbname)
		print(f"final GMM in text file: {gmmname[:-4]}_even/odd.txt")
		print(f"final GMM in density map: {avgname[:-4]}_even/odd.hdf")
		print(f"map-model FSC: {fscname[:-4]}_even/odd.txt")
		
	else:
		run(f"e2project3d.py {fname} --outfile {fname[:-4]}_tmp_projection.hdf --orientgen=eman:delta=4 --parallel=thread:16")
		run(f"e2gmm_refine_new.py --ptclsin {fname[:-4]}_tmp_projection.hdf --model {pdbname} --maxres {options.maxres} --minres {options.minres} --modelout {gmmname} --niter 40 --trainmodel --evalmodel {fname[:-4]}_tmp_model_projections.hdf --learnrate 1e-5")
		run(f"e2spa_make3d.py --input {fname[:-4]}_tmp_model_projections.hdf --output {avgname} --thread 32")
		run(f"e2proc3d.py {avgname} {avgname} --process mask.soft:outer_radius=-16 --matchto {fname}")
		run(f"e2proc3d.py {avgname} {fscname} --calcfsc {fname}")
	
		
		print("final pdb model: "+ pdbname)
		print("final GMM in text file: "+ gmmname)
		print("final GMM in density map: "+avgname)
		print("map-model FSC: "+fscname)
		
		os.remove(f"{fname[:-4]}_tmp_projection.hdf")
		os.remove(f"{fname[:-4]}_tmp_model_projections.hdf")
	
	E2end(logid)
	
	
if __name__ == '__main__':
	main()
