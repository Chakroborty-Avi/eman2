#!/usr/bin/env python
# Author: Steven Ludtke, 10/16/2010 (sludtke@bcm.edu)
# Copyright (c) 2000-2010 Baylor College of Medicine
#
# This software is issued under a joint BSD/GNU license. You may use the
# source code in this file under either license. However, note that the
# complete EMAN2 and SPARX software packages have some GPL dependencies,
# so you are responsible for compliance with the licenses of these packages
# if you opt to use BSD licensing. The warranty disclaimer below holds
# in either instance.
#
# This complete copyright notice must be included in any revised version of the
# source code. Additional authorship citations may be added, but existing
# author citations must be preserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  2111-1307 USA
#
#

from past.utils import old_div
from builtins import range
from EMAN2 import *
from optparse import OptionParser
import numpy as np
import scipy.fft as fft
import traceback
import cmath
import random

try:
	from PyQt5 import QtCore, QtGui, QtWidgets, QtOpenGL
	from PyQt5.QtCore import Qt
	from eman2_gui.emshape import *
	from eman2_gui.valslider import ValSlider,ValBox
	from eman2_gui.emimage import EMImageWidget
	from eman2_gui.emimage2d import EMImage2DWidget
	from eman2_gui.emplot2d import EMPlot2DWidget
	from eman2_gui.emapplication import EMApp
except:
	print("Unable to import Python GUI libraries, PYTHONPATH ?")
	sys.exit(1)

soundout=None

def fixang(x):
	x=fmod(x,360.0)
	if x>180.0: x-=360.0
	if x<=-180.0: x+=360.0
	return x

def initsound():
	global soundout
	if soundout!=None: return

	try:
		import sounddevice
	except:
		print("Unable to import sounddevice module. Please insure it is installed.")
		return

	try:
		soundout=sounddevice.OutputStream(samplerate=11025,channels=1,dtype="int16")
	except:
		traceback.print_exc()
		print("Unable to open output stream")
		return

def main():
	global debug,logid
	progname = os.path.basename(sys.argv[0])
	usage = """%prog [options]

This program allows the user to play around with Fourier synthesis graphically
	
"""

	parser = OptionParser(usage=usage,version=EMANVERSION)

#	parser.add_option("--gui",action="store_true",help="Start the GUI for interactive fitting",default=False)
	parser.add_option("--verbose", "-v", dest="verbose", action="store", metavar="n", type="int", default=0, help="verbose level [0-9], higher number means higher level of verboseness")
	
	(options, args) = parser.parse_args()

	app=EMApp()
	win=GUIFourierSynth(app)
	win.show()
	try: 
		win.raise_()
		win.synthplot.raise_()
	except: pass
	app.exec_()
	
class GUIFourierSynth(QtWidgets.QWidget):
	"""This class represents an application for interactive Fourier synthesis"""
	
	def __init__(self,app):
		self.app=app
		QtWidgets.QWidget.__init__(self,None)

		self.synthplot=EMPlot2DWidget(self.app)
		self.synthplot.show()

		self.fftplot=EMPlot2DWidget(self.app)	# not shown initially
		self.fftplot.show()

	#	self.bispecimg=EMImage2DWidget(self.app) # not shown initially
		
		# overall layout
		self.vbl1=QtWidgets.QVBoxLayout()
		self.setLayout(self.vbl1)
		
		# First row contains general purpose controls
		self.hbl1=QtWidgets.QHBoxLayout()
		self.vbl1.addLayout(self.hbl1)
		
		self.vcell=ValBox(self,(0,128.0),"Cell:",64)
		self.hbl1.addWidget(self.vcell)
		
		self.vncells=ValBox(self,(0,128.0),"n Cells:",1)
		self.hbl1.addWidget(self.vncells)
		
		self.voversamp=ValBox(self,(0,128.0),"Oversample:",1)
		self.hbl1.addWidget(self.voversamp)
		
		self.targfn=None
		
		self.vnsin=ValBox(self,(1,64),"# Sin:",32)
		self.vnsin.intonly=1
		self.hbl1.addWidget(self.vnsin)
		
		self.cbshowall=QtWidgets.QCheckBox("Show All")
		self.hbl1.addWidget(self.cbshowall)

		self.cbshifted=QtWidgets.QCheckBox("Shifted")
		self.hbl1.addWidget(self.cbshifted)

		self.bphaseleft=QtWidgets.QPushButton("\u2190")	# phase left
		self.hbl1.addWidget(self.bphaseleft)

		self.bphasecen=QtWidgets.QPushButton("O")
		self.hbl1.addWidget(self.bphasecen)

		self.bphaseright=QtWidgets.QPushButton("\u2192") # phase right
		self.hbl1.addWidget(self.bphaseright)

		self.cbtargfn=QtWidgets.QComboBox(self)
		self.cbtargfn.addItem("None")		# 0
		self.cbtargfn.addItem("triangle")	# 1
		self.cbtargfn.addItem("square")		# 2
		self.cbtargfn.addItem("square imp")	# 3
		self.cbtargfn.addItem("delta")		# 4
		self.cbtargfn.addItem("noise")
		self.cbtargfn.addItem("saw")
		self.cbtargfn.addItem("sin")
		self.cbtargfn.addItem("modsin")
		self.cbtargfn.addItem("modsin2")
		self.cbtargfn.addItem("modsin3")	#10
		self.cbtargfn.addItem("sin low")
		self.cbtargfn.addItem("doubledelta")
		self.cbtargfn.addItem("sin bad f")
		self.cbtargfn.addItem("sin bad f2")
		self.cbtargfn.addItem("0 phase")	#15
		self.cbtargfn.addItem("rand phase")
		self.hbl1.addWidget(self.cbtargfn)

		self.bsound=QtWidgets.QPushButton("Snd")
		self.hbl1.addWidget(self.bsound)
		
		# Widget containing valsliders
		self.wapsliders=QtWidgets.QWidget(self)
#		self.wapsliders.setMinimumSize(800,640)
		self.gblap=QtWidgets.QGridLayout()
		self.gblap.setSizeConstraint(QtWidgets.QLayout.SetMinAndMaxSize)
		self.gblap.setColumnMinimumWidth(0,250)
		self.gblap.setColumnMinimumWidth(1,250)
		self.wapsliders.setLayout(self.gblap)
		
		# ScrollArea providing view on slider container widget
		self.wapsarea=QtWidgets.QScrollArea(self)
		self.wapsarea.setWidgetResizable(True)
		self.wapsarea.setWidget(self.wapsliders)
		self.vbl1.addWidget(self.wapsarea)

		self.vcell.valueChanged.connect(self.recompute)
		self.vncells.valueChanged.connect(self.recompute)
		self.voversamp.valueChanged.connect(self.recompute)
		self.vnsin.valueChanged.connect(self.nsinchange)
		self.cbshowall.stateChanged[int].connect(self.recompute)
		self.cbshifted.stateChanged[int].connect(self.recompute)
		self.cbtargfn.activated[int].connect(self.newtargfn)
		self.bphaseleft.clicked.connect(self.phaseleft)
		self.bphasecen.clicked.connect(self.phasecen)
		self.bphaseright.clicked.connect(self.phaseright)
		self.bsound.clicked.connect(self.playsound)


		self.wamp=[]
		self.wpha=[]
		self.curves=[]
		self.xvals=[]
		for i in range(65):
			self.wamp.append(ValSlider(self,(0.0,1.0),"%2d:"%i,0.0))
			self.gblap.addWidget(self.wamp[-1],i,0)
			self.wamp[-1].valueChanged.connect(self.recompute)
			
			self.wpha.append(ValSlider(self,(-180.0,180.0),"%2d:"%i,0.0))
			self.gblap.addWidget(self.wpha[-1],i,1)
			self.wpha[-1].valueChanged.connect(self.recompute)
		
			self.curves.append(EMData(64,1))
		
#			if self.cbshowall.isChecked() :
#				self.synthplot
		self.total=EMData(64,1)
	
		self.nsinchange()

	def phaseleft(self,v):	# fixed translation in minus direction
		sft=360.0/len(self.xvals)
		for i in range(1,len(self.wpha)):
			self.wpha[i].setValue(fixang(self.wpha[i].getValue()-sft*i),1)
		self.recompute()
			
	def phasecen(self,v):	# translation so phase of lowest freqeuncy is zero
		sft=self.wpha[1].getValue()
		for i in range(1,len(self.wpha)):
			self.wpha[i].setValue(fixang(self.wpha[i].getValue()-sft*i),1)
		self.recompute()

	def phaseright(self,v):	# fixed translation in plus direction
		sft=360.0/len(self.xvals)
		for i in range(1,len(self.wpha)):
			self.wpha[i].setValue(fixang(self.wpha[i].getValue()+sft*i),1)
		self.recompute()

	def playsound(self,v):
		global soundout
		initsound()
		soundout.start()
		soundout.write(self.assound)
		soundout.write(self.assound)
		soundout.stop()

		
	def newtargfn(self,index):
		"This function has a number of hardcoded 'target' functions"
	
		if index==0 : 
			self.targfn=None
			nsin=int(self.vnsin.getValue())
			for i in range(nsin+1): 
				self.wamp[i].setValue(0,1)
				self.wpha[i].setValue(0,1)

		elif index==15:		# zero phase
			nsin=int(self.vnsin.getValue())
			for i in range(nsin+1): 
				self.wpha[i].setValue(0,1)

		elif index==16:		# random phase
			nsin=int(self.vnsin.getValue())
			for i in range(nsin+1): 
				self.wpha[i].setValue(random.uniform(-180.,180.),1)
		else :
			nx=int(self.vcell.getValue())
			x=np.arange(0,1.0,1.0/nx)
			y=np.zeros(nx)
			
			if index==1 : 	# triangle
				y[:nx//2]=x[:nx//2]*2.0
				y[nx//2:]=(1.0-x[nx//2:])*2.0
			
			elif index==2 : # square
				y[:nx//4]=0
				y[nx//4:nx*3//4]=1.0
				y[nx*3//4:]=0
				
			elif index==3 : # square impulse
				y[:nx//2]=0
				y[nx//2:nx*3//5]=1.0
				y[nx*3//5:]=0
			
			elif index==4 : # delta
				y[:]=0
				y[nx//2]=10.0
				
			elif index==5 : # noise
				y=np.random.random_sample((nx,))-0.5
			
			elif index==6 : # saw
				y[:nx//4]=0
				y[nx//4:nx//2]=x[:nx//4]
				y[nx//2:nx*3//4]=-x[:nx//4]
				y[nx*3//4:]=0
				
			elif index==7 : # sin
				y=np.sin(x*16.0*pi)
			
			elif index==8 : # modulated sine
				y=np.sin(x*4.0*pi)*np.sin(x*32.0*pi)

			elif index==9 : # modulated sine 2
				y=np.sin(x*2.0*pi)*np.sin(x*32.0*pi)

			elif index==10 : # modulated sine 3
				y=np.sin(x*8.0*pi)*np.sin(x*32.0*pi)

			elif index==11 : # sin low
				y=np.sin(x*4.0*pi)

			elif index==12 : # double delta
				y[:]=0
				y[16]=5.0
				y[48]=5.0

			elif index==13 : # sin bad f
				y=np.sin(x*2.3*pi)
			
			elif index==14 : # sin bad f2
				y=np.sin(x*17.15*pi)
			
			self.targfn=y
			self.target2sliders()
		
		self.recompute()

	def target2sliders(self):
		f=fft.rfft(self.targfn)*2.0/len(self.targfn)
		nsin=int(self.vnsin.getValue())
		
		for i in range(min(len(f),nsin+1)):
#			print fft[i]
			amp=abs(f[i])
			if fabs(amp)<1.0e-6 : amp=0.0
			if amp==0 : pha=0
			else: pha=cmath.phase(f[i])
			self.wamp[i].setValue(amp,quiet=1)
			self.wpha[i].setValue(fixang(pha*180.0/pi),quiet=1)


	def nsinchange(self,value=None):
		if value==None : value=int(self.vnsin.getValue())
		
		for i in range(65):
			if i>value: 
				self.wamp[i].hide()
				self.wpha[i].hide()
			else :
				self.wamp[i].show()
				self.wpha[i].show()
		
		if self.targfn!=None :
			self.target2sliders()
			
		self.recompute()
	
	def recompute(self,value=None):
		nsin=int(self.vnsin.getValue())
		cell=int(self.vcell.getValue())
		ncells=int(self.vncells.getValue())
		oversamp=max(1,int(self.voversamp.getValue()))
		samples=int(cell*oversamp)
		
		# arrays since we're using them several ways
		self.svals=np.array([cmath.rect(self.wamp[i].getValue(),self.wpha[i].getValue()*pi/180.0) for i in range(nsin+1)])
		#self.wamps=np.array([v.getValue() for v in self.wamp[:nsin+1]])
		#self.wphas=np.array([v.getValue() for v in self.wpha[:nsin+1]])

		self.xvals=np.array([xn/float(oversamp) for xn in range(samples)])
		if samples//2>len(self.svals): svals=np.concatenate((self.svals,np.zeros(1+samples//2-len(self.svals))))
		else: svals=self.svals
		self.total=fft.irfft(svals)*(len(svals)-1)
		if ncells>1: self.total=np.tile(self.total,ncells)
		
		self.synthplot.set_data((np.arange(0,len(self.total)/oversamp,1.0/oversamp),self.total),"Sum",replace=True,quiet=True,linewidth=2)
		
		if not self.targfn is None:
			self.synthplot.set_data((np.arange(len(self.targfn)),self.targfn),"Target",quiet=True,linewidth=1,linetype=2,symtype=0)
		
#		if self.cbshowall.isChecked() :
#			csum=self.total["minimum"]*1.1
#			for i in range(nsin):
#				if self.wamps[i]==0: continue
#				csum-=self.wamps[i]*1.1
#				if self.cbshifted.isChecked() : self.curves[i].add(csum)
#				self.synthplot.set_data((self.xvals,self.curves[i].get_data_as_vector()),"%d"%i,quiet=True,linewidth=1,color=2)
#				csum-=self.wamps[i]*1.1

		self.synthplot.updateGL()

		self.fftplot.set_data((np.arange(len(self.svals)),np.abs(self.svals)),"Amp",color=0,linetype=0,linewidth=2)
		self.fftplot.set_data((np.arange(len(self.svals)),np.angle(self.svals)),"Pha",color=1,linetype=0,linewidth=2)
		self.fftplot.updateGL()

		self.assound=np.tile((self.total*10000.0).astype("int16"),200)
		
if __name__ == "__main__":
	main()
	
