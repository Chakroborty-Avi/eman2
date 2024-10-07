#!/usr/bin/env python
# Muyuan Chen 2020-03
from EMAN2 import *
from EMAN2_utils import *
import numpy as np
from sklearn import cluster,mixture
from sklearn.decomposition import PCA
import scipy.spatial.distance as scipydist

def main():
	
	usage=" "
	parser = EMArgumentParser(usage=usage,version=EMANVERSION)
	parser.add_argument("--pts", type=str,help="point input", default="")
	parser.add_argument("--pcaout", type=str,help="pca output", default="")
	parser.add_argument("--ptclsin", type=str,help="ptcl input", default="")
	parser.add_argument("--ptclsout", type=str,help="ptcl out suffix", default="")
	parser.add_argument("--pad", type=int,help="pad for make3d", default=-1)
	parser.add_argument("--ncls", type=int,help="number of classes", default=3)
	parser.add_argument("--nbasis", type=int,help="PCA dimensionality", default=2)
	parser.add_argument("--width", type=float,help="width of the vector. 1 covers all points. default 0.98", default=.99)
	parser.add_argument("--setsf", type=str,help="setsf", default="")
	parser.add_argument("--mode", type=str,help="classify/regress", default="classify")
	parser.add_argument("--axis", type=str,help="axis for regress. one number for a line, and two numbers separated by comma to draw circles.", default='0')
	parser.add_argument("--sym", type=str,help="symmetry", default="c1")
	parser.add_argument("--nptcl", type=int,help="number of particles per class in regress mode", default=2000)
	parser.add_argument("--apix", type=float,help="overwrite apix for pdb morphing", default=-1)
	parser.add_argument("--decoder", type=str,help="decoder input", default=None)
	parser.add_argument("--pdb", type=str,help="model input in pdb", default=None)
	parser.add_argument("--selgauss", type=str,help="provide a text file of the indices of gaussian (or volumic mask) that are allowed to move", default=None)
	parser.add_argument("--model00", type=str,help="neutral state model. require if --decoder and --selgauss are provided", default=None)
	parser.add_argument("--outsize", type=int,help="box size of 3d volume output", default=-1)

	parser.add_argument("--skip3d", action="store_true", default=False ,help="skip the make3d step.")
	parser.add_argument("--umap", action="store_true", default=False ,help="use umap instead of pca.")
	parser.add_argument("--fulldist", action="store_true", default=False ,help="use full distance in reduced space instead of project to one axis.")

	parser.add_argument("--spt", action="store_true", default=False ,help="mode for subtomogram particles.")

	parser.add_argument("--threads", default=32,type=int,help="Number of threads to run in parallel on a single computer. This is the only parallelism supported by e2make3dpar")
	parser.add_argument("--ppid", type=int, help="Set the PID of the parent process, used for cross platform PPID",default=-1)
	(options, args) = parser.parse_args()
	logid=E2init(sys.argv)
	
	pts=np.loadtxt(options.pts)
	
	if options.umap:
		
		import umap
		pca=umap.UMAP(n_components=options.nbasis)
		p2=pca.fit_transform(pts[:,1:])
		p2-=np.mean(p2, axis=0)
	else:
		pca=PCA(options.nbasis)
		p2=pca.fit_transform(pts[:,1:])
	
	if options.pcaout:
		np.savetxt(options.pcaout, p2)

	if options.mode=="classify":
		clust=cluster.KMeans(options.ncls)
		lbs=clust.fit_predict(p2)
		lbunq=np.unique(lbs)
		
	else:
		axis=[int(i) for i in options.axis.split(',')]
		print('regress along axis', axis)
		if len(axis)==1:
			p=p2[:,axis[0]]
			rg=np.arange(options.ncls)
			rg=rg/np.max(rg)-.5
			mx=2*np.sort(abs(p))[int(len(p)*options.width)]
			rg=rg*mx+np.mean(p)
			rg=rg[:,None]
			print(rg)
			
		else:
			p=np.linalg.norm(p2[:, axis], axis=1)
			mx=np.sort(abs(p))[int(len(p)*options.width)]
			t=np.arange(options.ncls)/options.ncls
			t=t*np.pi*2
			rg=np.array([np.cos(t), np.sin(t)]).T
			rg*=mx
			print(rg)
			
	if options.decoder :
		px=np.zeros((options.ncls, options.nbasis))
		for i,a in enumerate(axis): px[:,a]=rg[:,i]
		py=pca.inverse_transform(px).astype(np.float32)
		#print(py)
		if "CUDA_VISIBLE_DEVICES" not in os.environ:
			os.environ["CUDA_VISIBLE_DEVICES"]='0' 
		import tensorflow as tf
		
		emdir=e2getinstalldir()
		sys.path.insert(0,os.path.join(emdir,'bin'))
		from e2gmm_refine_new import ResidueConv2D,make_mask_gmm
		decode_model=tf.keras.models.load_model(options.decoder,compile=False,custom_objects={"ResidueConv2D":ResidueConv2D})
		pcnt=decode_model(py).numpy()
		p00=np.loadtxt(options.model00)
		# pcnt=pcnt-p00
		
		if options.selgauss:
			imsk=make_mask_gmm(options.selgauss, p00).numpy()
			print("Seleting {} out of {} Gaussians".format(np.sum(imsk), len(p00)))
			pcnt*=imsk[None,:,None]
			
		if options.pdb:
			
			#print(pcnt.shape)
			
			pdb=pdb2numpy(options.pdb, allatom=True)
			e=EMData(options.ptclsin)
			apix=e["apix_x"]
			if options.apix>0:
				apix=options.apix
			sz=e["nx"]
			pdb=pdb/e["ny"]/apix-0.5
			pdb[:,1:]*=-1
			
			print("Making distance matrix of ({},{})".format(len(pdb), len(p00)))
			dstmat=scipydist.cdist(pdb,p00[:,:3])
			dstmat=np.exp(-(dstmat**2)*500)
			dstmat[dstmat<.1]=0
			dstmat/=np.sum(dstmat, axis=1)[:,None]

			allpts=[]
			for i,v0 in enumerate(pcnt):
				v=np.dot(dstmat, v0)    

				pz=pdb+v[:,:3]
				pz[:,1:]*=-1
				pz=(pz+.5)*e["ny"]*apix
				allpts.append(pz.copy())
				pdbname= f"{options.ptclsout[:-4]}_{i:02d}.pdb"
				replace_pdb_points(options.pdb, pdbname, pz)
				print("pdb saved to {}".format(pdbname))

			d=allpts[-1]-allpts[0]
			d=np.linalg.norm(d, axis=1)
			print("RMSD {:.2f} from the first to the last frame".format(np.sqrt(np.mean(d**2))))
		
		else:
			for i,v0 in enumerate(pcnt):
				tname=f"{options.ptclsout[:-4]}_{i:02d}.txt"
				np.savetxt(tname, v0+p00)
				print("model saved to {}".format(tname))
		
	onames=[]
	fname=options.ptclsin
	lin=load_lst_params(fname)
		
	if options.spt:
		print(len(lin), p2.shape)

		pids=np.array([a["ptcl3d_id"] for a in lin])
		uid=np.unique(pids)
		p3did=[np.where(pids==u)[0] for u in uid]
		print(len(uid), "3D particles")

	lout=[]
	for j in range(options.ncls):
		
		
		if options.mode=="classify":
			l=lbunq[j]
			ii=np.where(lbs==l)[0]
			print(j, len(ii))
		else:
			if len(axis)==1 and options.fulldist==False:
				d=abs(p2[:,axis[0]]-rg[j])
			else:
				d=np.linalg.norm(p2[:,axis]-rg[j], axis=1)
				
			ii=np.argsort(d)[:options.nptcl]
			print(j, rg[j], d[ii[-1]])
		
		if options.spt:
			idx=[p3did[i] for i in ii]
			idx=np.concatenate(idx)
		else:
			idx=pts[ii,0].astype(int)

		print(len(ii), len(idx))
		lo=[lin[i].copy() for i in idx]
		for l in lo:
			l["class"]=j
		
		lout.extend(lo)
	
	save_lst_params(lout, options.ptclsout)
	print(f"Particle list saved in {options.ptclsout}")
	
	if options.skip3d==False:
		e=EMData(fname, 0, True)
		if options.outsize<0:
			options.outsize=e["nx"]
		if options.pad<1: options.pad=good_size(e["nx"]*1.25)
		if options.setsf:
			options.setsf=" --setsf "+options.setsf
		
		name3d=options.ptclsout[:-4]+".hdf"
		if os.path.isfile(name3d):
			os.remove(name3d)
			
		for j in range(options.ncls):
			t="tmp_classify_{:04d}.hdf".format(np.random.randint(10000))
			cmd="e2spa_make3d.py --input {} --output {} --pad {} --outsize {} --keep 1 --parallel thread:{} {} --sym {} --clsid {}".format(options.ptclsout, t, options.pad, options.outsize, options.threads, options.setsf, options.sym, j)
			run(cmd)
			e=EMData(t)
			e.write_compressed(name3d,-1,12)
			os.remove(t)
			
		print(f"Density maps saved in {name3d}")
	E2end(logid)
	
	
if __name__ == '__main__':
	main()
	
