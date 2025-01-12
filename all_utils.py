## from builtin
import sys
import numpy as np 
import h5py
import os
import copy
import inspect

from scipy.optimize import leastsq as opt
from scipy.spatial.distance import cdist as cdist
from scipy.interpolate import interp1d

from matplotlib.ticker import NullFormatter

import inspect

#GLOBAL VARIABLES   

# Code mass -> g , (code length)^-3 -> cm^-3 , g -> nH
DENSITYFACT=2e43*(3.086e21)**-3/(1.67e-24)
HYDROGENMASS = 1.67e-24  # g
cm_per_kpc = 3.08e21 # cm/kpc
Gcgs = 6.674e-8 #cm3/(g s^2)
SOLAR_MASS_g = 1.989e33

## python helpers
def filter_kwargs(func,kwargs):
    good = {}
    bad = {}

    ## get the args that func takes
    allowed_args = inspect.getargspec(func)[0]
    for arg in kwargs.keys():
        ## ignore self if we're inspecting a method
        if arg == 'self':
            continue

        if arg in allowed_args:
            good[arg] = kwargs[arg]
        else:
            bad[arg] = kwargs[arg]
    return good,bad 

def append_function_docstring(function_1,function_2,**kwargs):
    #print(function_1,function_2)
    #print(function_1.__doc__,function_2.__doc__)
    function_1.__doc__ = append_string_docstring(
        function_1.__doc__,function_2,**kwargs)

def append_string_docstring(string,function_2,use_md=True,prepend_string=''):
    prepend_string += use_md*"### "
    name = function_2.__qualname__
    if use_md:
        name = '`' + name + '`' 

    string+="\n--------\n %s:\n %s"%(
        prepend_string + name,
        function_2.__doc__)
    return string

    
def get_size(obj, seen=None):
    """Recursively finds size of objects
        https://goshippo.com/blog/measure-real-size-any-python-object/
    """
    size = sys.getsizeof(obj)
    if seen is None:
        seen = set()
    obj_id = id(obj)
    if obj_id in seen:
        return 0
    # Important mark as seen *before* entering recursion to gracefully handle
    # self-referential objects
    seen.add(obj_id)
    if isinstance(obj, dict):
        size += sum([get_size(v, seen) for v in obj.values()])
        size += sum([get_size(k, seen) for k in obj.keys()])
    elif hasattr(obj, '__dict__'):
        size += get_size(obj.__dict__, seen)
    elif hasattr(obj, '__iter__') and not isinstance(obj, (str, bytes, bytearray)):
        size += sum([get_size(i, seen) for i in obj])
    return size

def suppressSTDOUTToFile(fn,args,fname,mode='a+',debug=1):
    """Hides the printed output of a python function to remove clutter, but
        still saves it to a file for later inspection. 
        Input: 
            fn - The function you want to call 
            args - A dictionary with keyword arguments for the function
            fname - The path to the output text file you want to pipe to. 
            mode - The file open mode you want to use, defaults to a+ to append
                to the same debug/output file but you might want w+ to replace it
                every time. 
            debug - Prints a warning message that the STDOUT is being suppressed
        Output: 
            ret - The return value of fn(**args)
    """
    
    orgstdout=sys.stdout
    ret=-1
    try:
        handle=StringIO.StringIO()
        if debug:
            print('Warning! Supressing std.out...')
        sys.stdout=handle

        ret=fn(**args)

        with file(fname,mode) as fhandle:
            fhandle.write(handle.getvalue())
    finally:
        sys.stdout=orgstdout
        if debug:
            print('Warning! Unsupressing std.out...')

    return ret

def suppressSTDOUT(fn,args,debug=1):
    """Hides the printed output of a python function to remove clutter. 
        Input: 
            fn - The function you want to call 
            args - A dictionary with keyword arguments for the function
            debug - Prints a warning message that the STDOUT is being suppressed
        Output: 
            ret - The return value of fn(**args)
    """
    orgstdout=sys.stdout
    ret=-1
    try:
        handle=StringIO.StringIO()
        if debug:
            print('Warning! Supressing std.out...')
        sys.stdout=handle

        ret=fn(**args)

    finally:
        sys.stdout=orgstdout
        if debug:
            print('Warning! Unsupressing std.out...')

    return ret

## dictionary helper functions
def filterDictionary(dict0,indices,dict1 = None,key_exceptions=[],free_mem = 0):
    if dict1 is None:
        dict1={}
    for key in dict0:
        if key in key_exceptions:
            continue
        try:
            if np.shape(dict0[key])[0]==indices.shape[0]:
                dict1[key]=dict0[key][indices]
            ## should only be center of mass and center of mass velocity
            else:
                raise Exception("Save this array verbatim")
        except:
            dict1[key]=dict0[key]
    if free_mem:
        del dict0
    return dict1

#fitting functions
def fitAXb(xs,ys,yerrs):
    """Fits a linear trendline to some data"""
    if yerrs==None:
        yerrs=np.array([1]*len(xs))
    weights=yerrs**-2.
    X=np.matrix([[sum(ys*weights)],[sum(xs*ys*weights)]])
    M=np.matrix([
        [sum(weights),sum(xs*weights)],
        [sum(xs*weights),sum(xs**2.*weights)]
        ])
    [y0],[a]=(M.I*X).A
    return a,y0

def fit_running_AXb(time_edges,boxcar_width,xs,ys,yerrs):
    """fits a trendline using f(x) ~ y in bins 
    of t that are boxcar_width wide"""
    
    xs,ys = pairReplace(xs,ys,np.nan,np.isinf)
    if yerrs==None:
        yerrs=np.ones(len(xs))
    weights=yerrs**-2.
    
    boxcar_xs,sum_weights = boxcar_average(
        time_edges,
        weights,
        boxcar_width,
        average=False)
    
    boxcar_xs,sum_xs_weights = boxcar_average(
        time_edges,
        xs*weights,
        boxcar_width,
        average=False)
    
    boxcar_xs,sum_xs2_weights = boxcar_average(
        time_edges,
        xs*xs*weights,
        boxcar_width,
        average=False)
    
    boxcar_xs,sum_ys_weights = boxcar_average(
        time_edges,
        ys*weights,
        boxcar_width,
        average=False)
    
    boxcar_xs,sum_ys_xs_weights = boxcar_average(
        time_edges,
        ys*xs*weights,
        boxcar_width,
        average=False)


    X = np.zeros((sum_ys_weights.size,2))
    X[:,0] = sum_ys_weights
    X[:,1] = sum_ys_xs_weights
    
    M = np.zeros((sum_weights.size,2,2))
    M[:,0,0] = sum_weights
    M[:,0,1] = sum_xs_weights
    M[:,1,0] = sum_xs_weights
    M[:,1,1] = sum_xs2_weights

    test_arr = sum_xs_weights==0
    if np.any(test_arr):
        inds = np.argwhere(test_arr)[:,0]
        M[test_arr] = [[np.nan,np.nan],[np.nan,np.nan]]
    
    #print("X=",X[4399])
    #print("M=",M[4399])
    try:
        invs = np.linalg.inv(M)
    except:
        ## one of the matrices was singular... 
        ##  none should have 0 pivots so is 
        ##  that just bad luck...? overflow error?
        ##  who could say. regardless, this will do
        ##  **something**
        invs = np.linalg.inv(M)
    
    ### https://stackoverflow.com/questions/46213851/python-multiplying-a-list-of-vectors-by-a-list-of-matrices-as-a-single-matrix-o
    ##  only god knows why this works
    pars = np.einsum('ij,ikj->ik',X,invs)
    fit_bs, fit_as = pars.T
    return fit_as,fit_bs

def fitVoigt(xs,ys,yerrs=None):
    p0 = [np.sum(xs*ys)/np.sum(ys),
        (np.max(xs)-np.min(xs))/4.,
        (np.max(xs)-np.min(xs))/4.,
        np.max(ys)]

    ## define a gaussian with amplitude A, mean mu, and width sigma
    lorentz_fn = lambda pars,x: (pars[3]*
        pars[2]/(
        (x-pars[0])**2 + pars[2]**2) )

    gauss_fn = lambda pars,x: pars[3]/np.sqrt(
        2*np.pi*pars[1]**2
        )*np.exp(-(x-pars[0])**2./(2*pars[1]**2.))

    fn = lambda pars,x: lorentz_fn(pars,x)*gauss_fn(pars,x)


    pars = fitLeastSq(fn,p0,xs,ys,yerrs)
    return pars,lambda x: fn(pars,x)


def fitLorentzian(xs,ys,yerrs=None):
    p0 = [np.sum(xs*ys)/np.sum(ys),(np.max(xs)-np.min(xs))/4.,np.max(ys)]

    ## define a gaussian with amplitude A, mean mu, and width sigma
    fn = lambda pars,x: pars[2]*(np.pi*pars[1])**-1*(pars[1]**2/(
        (x-pars[0])**2 + pars[1]**2) )

    pars = fitLeastSq(fn,p0,xs,ys,yerrs)
    return pars,lambda x: fn(pars,x)
    
def fitGauss(xs,ys,yerrs=None,format_str=None):
    ## initial parameter estimate
    p0 = [np.sum(xs*ys)/np.sum(ys),(np.max(xs)-np.min(xs))/4.,np.max(ys)]

    ## define a gaussian with amplitude A, mean mu, and width sigma
    fn = lambda pars,x: pars[2]*np.exp(-(x-pars[0])**2./(2*pars[1]**2.))

    pars = fitLeastSq(fn,p0,xs,ys,yerrs)
    if format_str is None:
        pass
    return pars,lambda x: fn(pars,x)


def covarianceEigensystem(xs,ys):
    """ calculates the covariance matrix and the principle axes
        (eigenvectors) of the data. 
        Eigenvalues represent variance along those principle axes.

        ## choose new x-axis to be evecs[0], rotation angle is
        ##  angle between it and old x-axis, i.e.
        ##  ehat . xhat = cos(angle)
        angle = np.arccos(evecs[0][0])

        ## evals are variance along principle axes
        rx,ry = evals**0.5 ## in dex
        cx,cy = 10**np.mean(xs),10**np.mean(ys) ## in linear space

        for evec,this_eval in zip(evecs,evals):
            dx,dy = evec*this_eval**0.5
            ax.plot(
                [cx,10**(np.log10(cx)+dx)],
                [cy,10**(np.log10(cy)+dy)],
                lw=3,ls=':',c='limegreen')

        plotEllipse(
            ax,
            cx,cy,
            rx,ry,
            angle=angle*180/np.pi,
            log=True,
            color='limegreen')"""

    if len(xs) == len(ys) == 0:
        return np.array([[np.nan,np.nan],[np.nan,np.nan]]),np.array([np.nan,np.nan])
    cov = np.cov([xs,ys])
    evals,evecs = np.linalg.eig(cov)

    evecs = evecs.T ## after transpose becomes [e1,e2], which makes sense...? lol

    ## re-arrange so semi-major axis is always 1st
    sort_mask = np.argsort(evals)[::-1]
    evals,evecs = evals[sort_mask],evecs[sort_mask]
    evecs[np.all(evecs<0,axis=1)]*=-1 ## take the positive version

    return evecs,evals

def getCovarianceEllipse(xs,ys):
    evecs,evals = covarianceEigensystem(xs,ys)

    ## choose new x-axis to be evecs[0], rotation angle is
    ##  angle between it and old x-axis, i.e.
    ##  ehat . xhat = cos(angle)
    angle = np.arccos(evecs[0][0])

    ## evals are variance along principle axes
    rx,ry = evals**0.5 ## in dex
    cx,cy = 10**np.mean(xs),10**np.mean(ys) ## in linear space

    return cx,cy,rx,ry,angle,evecs


def fitSkewGauss(xs,ys,yerrs=None):
    ## initial parameter estimate
    p0 = [np.sum(xs*ys)/np.sum(ys),(np.max(xs)-np.min(xs))/4.,np.max(ys),.5]

    ## define a gaussian with amplitude A, mean mu, and width sigma
    fn = lambda pars,x: pars[2]*np.exp(-(x*pars[3]-pars[0])**2./(2*pars[1]**2.))

    pars = fitLeastSq(fn,p0,xs,ys,yerrs)
    return pars,lambda x: fn(pars,x)

def fitLeastSq(fn,p0,xs,ys,yerrs=None,log_fit=0):
    """ Example fitting a parabola:
        fn = lambda p,xs: p[0]+p[1]*xs**2
        xs,ys=np.arange(-10,10),fn((1,2),xs)
        plt.plot(xs,ys,lw=3)
        pars = fitLeastSq(fn,[15,2],xs,ys)
        plt.plot(xs,fn(pars,xs),'r--',lw=3)"""
    if yerrs is not None:
        if log_fit:
            fit_func= lambda p: np.log10(ys) - np.log10(fn(p,xs))
        else:
            fit_func= lambda p: (ys - fn(p,xs))/yerrs
    else:
        if log_fit:
            fit_func= lambda p: np.log10(ys) - np.log10(fn(p,xs))
        else:
            fit_func= lambda p: (ys - fn(p,xs))
    pars,res = opt(fit_func,p0)

    return pars
    
def modelVariance(fn,xs,ys,yerrs=None):
    """takes a function and returns the variance compared to some data"""
    if yerrs==None:
        yerrs=[1]*len(xs)
    return sum([(fn(x)-ys[i])**2./yerrs[i]**2. for i,x in enumerate(xs)])

def brokenPowerLaw(a1,b1,a2,b2,xoff,x):
    """A helper function to evaluate a broken power law given some
        parameters-- since lambda functions create unwanted aliases"""
    if x < xoff:
        return a1*x+b1
    else:
        return a2*x+b2

def fit_broken_AXb(xs,ys,yerrs=None):
    """Finds the best fit broken linear trendline for a set of x and y 
        data. It does this by finding the chi^2 of placing a joint at each 
        point and finding the best fit linear trendline for the data on either 
        side. The joint that produces the minimum chi^2 is accepted. 
        Input: 
            xs - the x values 
            ys - the y values 
            yerrs - the yerrors, defaults to None -> constant error bars
        Output: 
            what it advertises
    """
    vars=[]
    models=[]
    if yerrs==None:
        yerrs=np.array([1]*len(xs))
    for i,xoff in enumerate(xs):
        if i==0 or i==1 or i==(len(xs)-2) or i==(len(xs)-1):
            #skip the first  and second guy, lol
            continue
        b1,a1=fitAXb(xs[:i],ys[:i],yerrs[:i])
        b2,a2=fitAXb(xs[i:],ys[i:],yerrs[i:])
        params=(a1,b1,a2,b2,xoff)
        models+=[params]
        model=lambda x: brokenPowerLaw(params[0],params[1],params[2],params[3],
            params[4],x)
        vars+=[modelVariance(model,xs,ys,yerrs)]

    #there is a hellish feature of python that refuses to evaluate lambda functions
    #so i can't save the models in their own list, I have to save their parameters
    #and recreate the best model
    params=models[np.argmin(vars)]
    model=lambda x: brokenPowerLaw(params[0],params[1],params[2],params[3],
        params[4],x)
    return model,params

def fitExponential(xs,ys):
    """Fits an exponential log y = ax +b => y = e^b e^(ax)"""
    b,a = fitAXb(xs[ys>0],np.log(ys[ys>0]),yerrs=None)
    return (b,a)


#math functions (trig and linear algebra...)
def vectorsToRAAndDec(vectors):
    xs,ys,zs = vectors.T
    ## puts the meridian at x = 0
    ra = np.arctan2(ys,xs)

    ## puts the equator at z = 0
    dec = np.arctan2(zs,(xs**2+ys**2))

    return ra,dec

def rotateVectorsZY(thetay,thetaz,vectors):
    rotatedCoords=rotateVectors(rotationMatrixZ(thetaz),vectors)
    rotatedCoords=rotateVectors(rotationMatrixY(thetay),rotatedCoords)
    return rotatedCoords

def unrotateVectorsZY(thetay,thetaz,vectors):
    rotatedCoords=rotateVectors(rotationMatrixY(-thetay),vectors)
    rotatedCoords=rotateVectors(rotationMatrixZ(-thetaz),rotatedCoords)
    return rotatedCoords

def rotateVectors(rotationMatrix,vectors):
    return np.dot(rotationMatrix,vectors.T).T

def rotationMatrixY(theta):
    return np.array([
            [np.cos(theta),0,-np.sin(theta)],
            [0,1,0],
            [np.sin(theta),0,np.cos(theta)]
        ])

def rotationMatrixX(theta):
    return np.array([
            [1,0,0],
            [0,np.cos(theta),np.sin(theta)],
            [0,-np.sin(theta),np.cos(theta)]
        ])

def rotationMatrixZ(theta):
    return np.array([
            [np.cos(theta),np.sin(theta),0],
            [-np.sin(theta),np.cos(theta),0],
            [0,0,1]
        ])

def getThetasTaitBryan(angMom):
    """ as Euler angles but xyz vs. zxz"""
    theta_TB = np.arctan2(angMom[1],np.sqrt(angMom[0]**2+angMom[2]**2))*180/np.pi
    phi_TB = np.arctan2(-angMom[0],angMom[2])*180/np.pi

    #new_angMom = rotateEuler(
        #theta_TB,phi_TB,0,
        #angMom,
        #order='xyz',loud=False)
    #print('old:',angMom,'new:',new_angMom)

    ## RETURNS DEGREES
    return theta_TB,phi_TB

def rotateEuler(
    theta,phi,psi,
    pos,
    order='xyz', ## defaults to Tait-Bryan, actually
    recenter=False,
    rotation_point=None,
    loud=True,
    inverse=False):

    if rotation_point is None:
        rotation_point = np.zeros(3)
    pos=pos-rotation_point
    ## if need to rotate at all really -__-
    if theta==0 and phi==0 and psi==0:
        return pos
    # rotate particles by angle derived from frame number
    theta_rad = np.pi*theta/ 180
    phi_rad   = np.pi*phi  / 180
    psi_rad   = np.pi*psi  / 180

    c1 = np.cos(theta_rad)
    s1 = np.sin(theta_rad)
    c2 = np.cos(phi_rad)
    s2 = np.sin(phi_rad)
    c3 = np.cos(psi_rad)
    s3 = np.sin(psi_rad)

    # construct rotation matrix
    ##  Tait-Bryan angles
    if order == 'xyz':
        if loud:
            print('Using Tait-Bryan angles (xyz). Change with order=zxz.')
        rot_matrix = np.array([
            [c2*c3           , - c2*s3         , s2    ],
            [c1*s3 + s1*s2*c3, c1*c3 - s1*s2*s3, -s1*c2],
            [s1*s3 - c1*s2*c3, s1*c3 + c1*s2*s3, c1*c2 ]],
            dtype = np.float32)

    ##  classic Euler angles
    elif order == 'zxz':
        if loud:
            print('Using Euler angles (zxz). Change with order=xyz.')
        rot_matrix = np.array([
            [c1*c3 - c2*s1*s3, -c1*s3 - c2*c3*s1, s1*s2 ],
            [c3*s1 + c1*c2*s3, c1*c2*c3 - s1*s3 , -c1*s2],
            [s2*s3           , c3*s2            , c2    ]])
    else:
        raise Exception("Bad order")

    ## the inverse of a rotation matrix is its tranpose
    if inverse:
        rot_matrix = rot_matrix.T

    ## rotate about each axis with a matrix operation
    pos_rot = np.matmul(rot_matrix,pos.T).T

    ## on 11/23/2018 (the day after thanksgiving) I discovered that 
    ##  numpy will change to column major order or something if you
    ##  take the transpose of a transpose, as above. Try commenting out
    ##  this line and see what garbage you get. ridiculous.
    ##  also, C -> "C standard" i.e. row major order. lmfao
    pos_rot = np.array(pos_rot,order='C')
    
    ### add the frame_center back
    if not recenter:
        pos_rot+=rotation_point

    ## can never be too careful that we're float32
    return pos_rot

def applyRandomOrientation(coords,vels,random_orientation):
    ## interpret the random_orientation variable as a seed
    np.random.seed(random_orientation)

    ## position angles of random orientation vector 
    theta = np.arccos(1-2*np.random.random())
    phi = np.random.random()*2*np.pi

    ## convert from position angles to rotation angles
    orientation_vector = np.array([
        np.sin(theta)*np.cos(phi),
        np.sin(theta)*np.sin(phi),
        np.cos(theta)])
    new_theta,new_phi = getThetasTaitBryan(orientation_vector)

    ## rotate the coordinates and velocities 
    if coords is not None:
        coords = rotateEuler(new_theta,new_phi,0,coords,loud=False)
    if vels is not None:
        vels = rotateEuler(new_theta,new_phi,0,vels,loud=False)

    return orientation_vector,new_theta,new_phi,coords,vels

def rotateSnapshot(which_snap,theta,phi,psi):
    if 'Coordinates' in which_snap:
        which_snap['Coordinates']=rotateEuler(theta,phi,psi,which_snap['Coordinates'],loud=False)
    if 'Velocities' in which_snap:
        which_snap['Velocities']=rotateEuler(theta,phi,psi,which_snap['Velocities'],loud=False)
    return which_snap

#list operations
def substep(arr,N):
    """linearly interpolates between the values in array arr using N steps"""
    my_arr = np.array([])
    for lx,rx in zip(arr[:-1],arr[1:]):
        my_arr=np.append(my_arr,np.linspace(lx,rx,N+1)[:-1])
        
    ## excluded the right end, need to include the final right end
    my_arr = np.append(my_arr,rx)
    return my_arr

def manyFilter(bool_fn,*args):
    """filters an arbitrary number of arrays in 
        corresponding tuples by bool_fn"""
    mask = np.ones(args[0].size)

    for arg in args:
        mask = np.logical_and(bool_fn(arg),mask)

    return [arg[mask] for arg in args]

def pairReplace(xs,ys,value,bool_fn):
    """filters both x and y corresponding pairs by
        bool_fn"""

    xs,ys = copy.copy(xs),copy.copy(ys)

    xs[bool_fn(ys)] = value
    ys[bool_fn(ys)] = value

    xs[bool_fn(xs)] = value
    ys[bool_fn(xs)] = value

    return xs,ys

def pairFilter(xs,ys,bool_fn):
    """filters both x and y corresponding pairs by
        bool_fn"""

    new_xs = xs[bool_fn(ys)]
    new_ys = ys[bool_fn(ys)]

    new_ys = new_ys[bool_fn(new_xs)]
    new_xs = new_xs[bool_fn(new_xs)]
    return new_xs,new_ys

def findArrayClosestIndices(xs,ys):
    try:
        assert len(xs) < len(ys)
    except:
        raise ValueError(
            "Ys (%d)"%len(ys),
            "should be some large sample that",
            "Xs (%d) is subsampling!"%len(xs))

    dists = cdist(
        xs.reshape(-1,1),
        ys.reshape(-1,1))

    indices = np.argmin(dists,axis=1)
    return indices

def findIntersection(xs,ys,ys1):
    argmin = np.argmin((ys-ys1)**2)
    return xs[argmin],ys[argmin]

def getFWHM(xs,ys):
    argmax = np.argmax(ys)
    xl,yl = findIntersection(xs[:argmax],(ys/np.max(ys))[:argmax],0.5)
    xr,yr = findIntersection(xs[argmax:],(ys/np.max(ys))[argmax:],0.5)
    return (xr-xl),(xl,xr,yl,yr)
    

def boxcar_average(
    time_edges,
    ys,
    boxcar_width,
    loud=False,
    average=True, ## vs. just counting non-nan entries in a window
    edges = True):

    """
    for lists with many nans need to first run w/ average=False, then 
    run with ys=np.ones and average=False
    to get divisor for each window.

    idea is that you subtract off previous window from each window
    https://stackoverflow.com/questions/13728392/moving-average-or-running-mean
    def running_mean(x, N):
        cumsum = numpy.cumsum(numpy.insert(x, 0, 0)) 
        return (cumsum[N:] - cumsum[:-N]) / float(N)
    potentially accrues floating point error for many points... (>1e5?)
    there is another solution on that page that uses scipy instead 

    from scipy.ndimage.filters import uniform_filter1d
    uniform_filter1d(x, size=N) <--- requires one to explicitly deal 
        with edges of window
    """

    ## apply a finite filter... no infinities allowed!
    ys[np.logical_not(np.isfinite(ys))] = np.nan

    dts = np.unique(time_edges[1:]-time_edges[:-1])
    if not np.allclose(dts,dts[0]):
        print(dts)
        raise ValueError("ys must be uniformly spaced for this to work...")

    if not edges:
        time_edges = np.append([time_edges[0]-dts[0]],time_edges)

    ## number of points per boxcar is 
    N = int(boxcar_width//dts[0] + ((boxcar_width%dts[0])/dts[0]>=0.5))
    if loud:
        print("boxcar'ing with %d points/car, dt: %.2e window: %.2e"%(N,dts[0],boxcar_width))
    cumsum = np.nancumsum(np.insert(ys, 0, 0).astype(np.float64)) 

    ## cumsum[N:] is the first window, then second window + extra first point,
    ##  then third window + extra 2 first points, etc... 
    ys = (cumsum[N:]-cumsum[:-N])
    if average:
        ys = ys/N
    ys = np.append([np.nan]*(N-1),ys)
    return time_edges[:],ys
    
def smooth_x_varying_curve(xs,ys,smooth,log=False):

    if log:
        ys = np.log10(ys)

    times = np.arange(xs.max(),xs.min()-0.01,-0.01)[::-1]
    fn = interp1d(
        xs,
        ys,
        fill_value=np.nan,
        bounds_error=False)
    values = fn(times)

    smooth_xs,smooth_ys = boxcar_average(times,values,smooth)
    smooth_xs,smooth_ys2 = boxcar_average(times,values**2,smooth)

    ## have to skip first window's width of points
    skip_index = int(np.round(smooth/0.01))
    smooth_xs = smooth_xs[skip_index:]
    smooth_ys = smooth_ys[skip_index:]
    smooth_ys2 = smooth_ys2[skip_index:] 

    sigmas = (smooth_ys2-smooth_ys**2)**0.5


    if log:
        lowers = 10**(smooth_ys-sigmas)
        uppers = 10**(smooth_ys+sigmas)
        smooth_ys = 10**smooth_ys
        sigmas = 10**sigmas
        ys = 10**ys
    else:
        lowers = smooth_ys-sigmas
        uppers = smooth_ys+sigmas
    
    return smooth_xs,smooth_ys,sigmas,lowers,uppers
    
def find_local_minima_maxima(xs,ys,smooth=None,ax=None):

    ## calculate the slope of the curve
    slopes = np.diff(ys)/np.diff(xs)
    xs = xs[1:]

    ## smooth the slope if requested
    if smooth is not None:
        ## x could also be uniform and this will work
        xs,slopes,foo,bar,foo = smooth_x_varying_curve(xs,slopes,smooth)
    
    xs = xs[1:]
    ## find where slope changes sign
    zeros = xs[np.diff(slopes>0).astype(bool)]

    if ax is not None:
        ax.plot(xs,slopes[1:])
        ax.axhline(0,ls='--',c='k')
        #for zero in zeros:
            #ax.axvline(zero)

    return zeros
    
###### DIRECTORY STUFF ######
def add_directory_tree(datadir):
    """This function probably already exists lmfao..."""
    if not os.path.isdir(datadir):
        directories=datadir.split('/')
        directories_to_make=[]
        for i in xrange(len(directories)):
            trialdir='/'.join(directories[:-i])
            if os.path.isdir(trialdir):
                i-=1
                break
        for j in xrange(i):
            toadd='/'.join(directories[:-j-1])
            directories_to_make+=[toadd]
        directories_to_make+=[datadir]
        for directory_to_make in directories_to_make:
            os.mkdir(directory_to_make)

def getfinsnapnum(snapdir,getmin=0):
    if not getmin:
        maxnum = 0
        for snap in os.listdir(snapdir):
            if 'snapshot' in snap and 'hdf5' in snap and snap.index('snapshot')==0:
                snapnum = int(snap[len('snapshot_'):-len('.hdf5')])
                if snapnum > maxnum:
                    maxnum=snapnum
            elif 'snapdir' in snap:
                snapnum = int(snap[len('snapdir_'):])
                if snapnum > maxnum:
                    maxnum=snapnum
        return maxnum
    else:
        minnum=1e8
        for snap in os.listdir(snapdir):
            if 'snapshot' in snap and 'hdf5' in snap:
                snapnum = int(snap[len('snapshot_'):-len('.hdf5')])
                if snapnum < minnum:
                    minnum=snapnum
            elif 'snapdir' in snap:
                snapnum = int(snap[len('snapdir_'):])
                if snapnum < minnum:
                    minnum=snapnum
        return minnum

def extractMaxTime(snapdir):
    """Extracts the time variable from the final snapshot"""
    maxsnapnum = getfinsnapnum(snapdir)
    if 'snapshot_%3d.hdf5'%maxsnapnum in os.listdir(snapdir):
        h5path = 'snapshot_%3d.hdf5'%maxsnapnum
    elif 'snapdir_%03d'%maxsnapnum in os.listdir(snapdir):
        h5path = "snapdir_%03d/snapshot_%03d.0.hdf5"%(maxsnapnum,maxsnapnum)
    else:
        print("Couldn't find maxsnapnum in")
        print(os.listdir(snapdir))
        raise Exception("Couldn't find snapshot")

    with h5py.File(os.path.join(snapdir,h5path),'r') as handle:
        maxtime = handle['Header'].attrs['Time']
    return maxtime

## INDICES THOUGH
def extractRectangularVolumeIndices(rs,rcom,radius,height):
   x_indices = (rs-rcom)[:,0]**2<radius**2
   y_indices = (rs-rcom)[:,1]**2<radius**2

   height = radius if height==0 else height
   z_indices = (rs-rcom)[:,2]**2<height**2
   return np.logical_and(np.logical_and(x_indices,y_indices),z_indices)

def extractCylindricalVolumeIndices(coords,r,h,rcom=None):
    if rcom==None:
        rcom = np.array([0,0,0])
    gindices = np.sum((coords[:,:2])**2.,axis=1) < r**2.
    gzindices = (coords[:,2])**2. < h**2.
    indices = np.logical_and(gindices,gzindices)
    return indices

def extractSphericalVolumeIndices(rs,rcom,radius):
    return np.sum((rs - rcom)**2.,axis=1) < radius**2

## FIRE helper functions
def getSpeedOfSound(U_code):
    """U_code = snapdict['InternalEnergy'] INTERNAL ENERGY_code = VELOCITY_code^2 = (params.txt default = (km/s)^2)
        mu = mean molecular weight in this context
        c_s = sqrt(gamma kB T / mu)

        n kB T = (gamma - 1) U rho
        (gamma -1 ) U = kB T/mu = c_s^2/gamma
        c_s = sqrt(5/3 * 2/3 * U)
        """
    return np.sqrt(10/9.*U_code)

def getTemperature(
    U_code,
    helium_mass_fraction=None,
    ElectronAbundance=None,
    mu = None):
    """U_code = snapdict['InternalEnergy'] INTERNAL ENERGY_code = VELOCITY_code^2 = (params.txt default = (km/s)^2)
    helium_mass_fraction = snapdict['Metallicity'][:,1]
    ElectronAbundance= snapdict['ElectronAbundance']"""
    U_cgs = U_code*1e10 ## to convert from (km/s)^2 -> (cm/s)^2
    gamma=5/3.
    kB=1.38e-16 #erg /K
    m_proton=1.67e-24 # g
    if mu is None:
        ## not provided from chimes, hopefully you sent me helium_mass_fraction and
        ##  electron abundance!
        try: 
            assert helium_mass_fraction is not None
            assert ElectronAbundance is not None
        except AssertionError:
            raise ValueError(
                "You need to either provide mu or send helium mass fractions and electron abundances to calculate it!")
        y_helium = helium_mass_fraction / (4*(1-helium_mass_fraction)) ## is this really Y -> Y/4X
        mu = (1.0 + 4*y_helium) / (1+y_helium+ElectronAbundance) 
    mean_molecular_weight=mu*m_proton
    return mean_molecular_weight * (gamma-1) * U_cgs / kB

def get_IMass(age,mass,apply_factor=False):
    ## age must be in Gyr
    ## based off mass loss in gizmo plot, averaged over 68 stars
    b = 0.587
    a = -8.26e-2
    factors = b*age**a 
    factors[factors > 1]=1
    factors[factors < 0.76]=0.76
    if not apply_factor:
        return mass/factors
    else:
        return mass*factors

def getBolometricLuminosity(ageGyrs,masses):
    ## convert to Myr
    ageMyrs = ageGyrs*1000 

    ## initialize luminosity array
    lums = np.zeros(ageMyrs.size)
    lums[ageMyrs<3.5] = 1136.59 ## Lsun/Msun

    x = np.log10(ageMyrs[ageMyrs>=3.5]/3.5)
    lums[ageMyrs>=3.5] = 1500*np.exp(-4.145*x + 0.691*x**2 - 0.0576*x**3) ## Lsun/Msun
    ##  3.83e33 erg/s / 2e33 g =  1.915 cm^2 /s^2
    lums *= 1.915 ## erg/s / g = cm^2/s^2 

    return lums*masses ## erg/s code_mass/g, typically, or erg/s if masses is in g

def getLuminosityBands(ageGyrs,masses):
    """
    Then the bolometric Ψbol = 1136.59 for tMyr < 3.5, and 
    Ψbol = 1500 exp[−4.145x+0.691x2 −0.0576x3] 
    with x ≡ log10(tMyr/3.5) for tMyr > 3.5. 
    For the bands used in our radiation hydrodynamics, we have the following 
    intrinsic (before attenuation) bolometric corrections. 

    In the mid/far IR, ΨIR = 0. 

    In optical/NIR, Ψopt = fopt Ψbol with fopt = 0.09 for tMyr < 2.5; 
    fOpt = 0.09(1 + [(tMyr − 2.5)/4]2) for 2.5 < tMyr < 6; 
    fOpt = 1 − 0.841/(1 + [(tMyr − 6)/300]) for tMyr > 6. 

    For the photo-electric FUV band ΨFUV = 271[1+(tMyr/3.4)2] for tMyr < 3.4; 
    ΨFUV = 572(tMyr/3.4)−1.5 for tMyr > 3.4. 
    
    For the ionizing band Ψion = 500 for tMyr < 3.5; 
    Ψion = 60(tMyr/3.5)−3.6 + 470(tMyr/3.5)0.045−1.82 ln tMyr
    for 3.5 < tMyr < 25; Ψion = 0 for tMyr > 25. 
    
    The remaining UV luminosity, Ψbol − (ΨIR +Ψopt + ΨFUV + Ψion) 
    is assigned to the NUV band ΨNUV.
    """
    bolo_lums = getBolometricLuminosity(ageGyrs,masses)

def calculateKappa(vcs,rs):
    """calculate the epicyclic frequency"""
    
    dvcdr = (vcs[1:] - vcs[:-1])/(rs[1:]-rs[:-1])
    mid_rs = (rs[1:]+rs[:-1])/2.
    mid_vcs = (vcs[1:]+vcs[:-1])/2.
    kappas = np.sqrt(4*mid_vcs**2/mid_rs**2+mid_rs**2*dvcdr)
    kappa_fn = interp1d(mid_rs,kappas,fill_value="extrapolate",kind='linear')
    return kappa_fn(rs)

## USEFUL PHYSICS 
def calculateSigma1D(vels,masses):
    vcom = np.sum(vels*masses[:,None],axis=0)/np.sum(masses)
    vels = vels - vcom # if this has already been done, then subtracting out 0 doesn't matter
    v_avg_2 = (np.sum(vels*masses[:,None],axis=0)/np.sum(masses))**2
    v2_avg = (np.sum(vels**2*masses[:,None],axis=0)/np.sum(masses))
    return (np.sum(v2_avg-v_avg_2)/3)**0.5

def ff_timeToDen(ff_time):
    """ff_time must be in yr"""
    Gcgs = 6.67e-8 # cm^3 /g /s^2
    den = 3*np.pi/(32*Gcgs)/(ff_time * 3.15e7)**2 # g/cc
    return den 

def denToff_time(den):
    """den must be in g/cc"""
    Gcgs = 6.67e-8 # cm^3 /g /s^2
    ff_time = (
        3*np.pi/(32*Gcgs) /
        den  # g/cc
        )**0.5 # s

    ff_time /=3.15e7 # yr
    return ff_time

try:
    from numba import jit
    @jit(nopython=True)
    def get_cylindrical_velocities(vels,coords):
        this_coords_xy = coords[:,:2]
        this_radii_xy = np.sqrt(
            np.array([
                np.linalg.norm(this_coords_xy[pi,:]) for
                pi in range(len(this_coords_xy))])**2)

        rhats = np.zeros((len(this_coords_xy),2))
        rhats[:,0] = this_coords_xy[:,0]/this_radii_xy
        rhats[:,1] = this_coords_xy[:,1]/this_radii_xy

        vrs = np.sum(rhats*vels[:,:2],axis=1)
        #vrs = np.zeros(len(this_coords))
        #for pi in range(len(this_coords)):
            #vrs[pi] = np.sum(this_coords[pi,:2]/np.sum

        vzs = vels[:,2]

        vphis = np.sqrt(
            np.array([
                np.linalg.norm(vels[i,:]) for
                i in range(len(vels))
            ])**2 -
            vrs**2 -
            vzs**2)
        return vrs,vphis,vzs
except ImportError:
    print("Couldn't import numba. Missing:")
    print("abg_python.all_utils.get_cylindrical_velocities")

def getVcom(masses,velocities):
    assert np.sum(masses) > 0 
    return np.sum(masses[:,None]*velocities,axis=0)/np.sum(masses)

def iterativeCoM(coords,masses,n=4,r0=np.array([0,0,0])):
    rcom = r0
    radius = 1e10
    for i in range(n):
        mask = extractSphericalVolumeIndices(coords,rcom,radius)
        rcom = np.sum(coords[mask]*masses[mask][:,None],axis=0)/np.sum(masses[mask])
        print(radius,rcom)
        radius = 1000/3**i
    return rcom

def getAngularMomentum(vectors,masses,velocities):
    return np.sum(np.cross(vectors,masses[:,None]*velocities),axis=0)

def getAngularMomentumSquared(vectors,masses,velocities):
    ltot = np.sum(# sum in quadrature |lx|,|ly|,|lz|
        np.sum( # sum over particles 
            np.abs(np.cross( # |L| = |(r x mv )|
                vectors,
                masses[:,None]*velocities))
            ,axis=0)**2
        )**0.5 # msun - kpc - km/s units of L

    return ltot**2

    Li = np.cross(vectors,masses[:,None]*velocities)
    L2i = np.sum(Li*Li,axis=1)

    return np.sum(L2i)


