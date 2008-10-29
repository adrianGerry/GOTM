#$Id: common.py,v 1.13 2008-10-29 14:27:51 jorn Exp $

# Import modules from standard Python library
import sys,os.path,UserDict,re,xml.dom.minidom,datetime

# Import additional third party modules
import matplotlib.dates,numpy

import xmlstore.xmlstore

# ------------------------------------------------------------------------------------------
# Functions for getting/settings the path to data files
# ------------------------------------------------------------------------------------------
        
dataroot = None
def setDataRoot(path):
    global dataroot
    dataroot = path
def getDataRoot():
    global dataroot
    if dataroot==None:
        if hasattr(sys,'frozen'):
            dataroot = os.path.join(os.path.dirname(unicode(sys.executable, sys.getfilesystemencoding())),'xmlplot')
        else:
            dataroot = os.path.realpath(os.path.dirname(__file__))
    return dataroot
xmlstore.xmlstore.Schema.knownpaths['xmlplot'] = getDataRoot()

# ------------------------------------------------------------------------------------------
# Date-time functions
# ------------------------------------------------------------------------------------------

date2num = matplotlib.dates.date2num
num2date = matplotlib.dates.num2date
    
# ------------------------------------------------------------------------------------------
# Unit string convertor
# ------------------------------------------------------------------------------------------

def convertUnitToUnicode(unit):
    """Uses unicode to replace some common ASCII representations of
    degrees/subscript/superscript.
    """
    deg  = unichr(176)
    if unit=='celsius' or unit=='degC': return deg+'C'
    if unit in ('degrees_north','degree_north','degree_N','degrees_N','degreeN','degreesN'): return deg+'North'
    if unit in ('degrees_east', 'degree_east' ,'degree_E','degrees_E','degreeE','degreesE'): return deg+'East'
    sup2 = unichr(178)
    sup3 = unichr(179)
    unit = unit.replace('s2','s'+sup2)
    unit = unit.replace('s3','s'+sup3)
    unit = unit.replace('m2','m'+sup2)
    unit = unit.replace('m3','m'+sup3)
    unit = unit.replace('**2',sup2)
    unit = unit.replace('^2',sup2)
    unit = unit.replace('**3',sup3)
    unit = unit.replace('^3',sup3)
    return unit

# ------------------------------------------------------------------------------------------
# Numerical helper utilities
# ------------------------------------------------------------------------------------------

def findIndices(bounds,data):
    """Look for boundary indices of array based on desired value range.
    """
    # Zero-based indices!
    start = 0
    stop = len(data)-1
    if bounds!=None:
        if bounds[0]!=None:
            while start<len(data) and data[start]<bounds[0]: start+=1
        if bounds[1]!=None:
            while stop>=0         and data[stop] >bounds[1]: stop-=1

        # Greedy: we want take the interval that fully encompasses the specified range.
        if start>0 and start<len(data):  start-=1
        if stop<len(data)-1 and stop>=0: stop +=1

        # Note: a start beyond the available range, or a stop before it, will now have resulted
        # in start index > stop index, i.e., an invalid range. The calling function must be able
        # to handle this scenario.
        
    return (start,stop)

def interp1(x,y,X):
    """1D linear inter- and extrapolation. Operates on first axis.
    """
    assert x.ndim==1, 'Original coordinates must be supplied as 1D array.'
    assert X.ndim==1, 'New coordinates must be supplied as 1D array.'
    
    # Transpose because it is easiest in numpy to operate on last axis. (this because of
    # upcasting rules)
    y = y.transpose()
    
    # Create array to hold interpolated values
    Y = numpy.empty(y.shape[0:-1]+(X.shape[0],),y.dtype)
    
    # Find indices of interpolated X in original x.
    iX = x.searchsorted(X)
    
    # Get the bounds of valid indices (index<=0 means point before x-data, index>=x.shape[0]
    # means point beyond x-data)
    bounds = iX.searchsorted((0.5,x.shape[0]-0.5))
    
    # Shortcuts to indices for left and right bounds, and the left bound values.
    iX_high = iX[bounds[0]:bounds[1]]
    iX_low = iX_high-1
    x_low  = x[iX_low]
    y_low = y[...,iX_low]
    
    # Linear interpolation
    Y[...,bounds[0]:bounds[1]] = y_low + ((X[bounds[0]:bounds[1]]-x_low)/(x[iX_high]-x_low))*(y[...,iX_high]-y_low)
    
    # Set points beyond bounds to extreme values.
    Y[...,0:bounds[0]] = y.take((0,),-1)
    Y[...,bounds[1]:] = y.take((-1,),-1)
    
    # Undo the original transpose and return
    return Y.transpose()

def ndgrid(*coords):
    lens = [len(c) for c in coords]
    #ind = numpy.mgrid[tuple([slice(n) for n in lens])]
    #return [g[i] for g,i in zip(coords,ind)]
    newcoords = []
    for i,c in enumerate(coords):
        newc = numpy.empty(lens,dtype=c.dtype)
        newc_view = newc.swapaxes(i,0)
        newc_view[...] = c
        newcoords.append(newc)
    return newcoords

def getCenters(data,addends=False):
    delta = (data[1:]-data[:-1])/2
    newdata = data[:-1]+delta
    if addends: newdata = numpy.concatenate(([data[0]-delta[0]],newdata,[data[-1]+delta[-1]]),0)
    return newdata

def replicateCoordinates(coords,data,idim):
    assert coords.ndim==1, 'Coordinate array must be one-dimensional.'
    assert coords.shape[0]==data.shape[idim], 'Length of coordinate vector (%i) and specified dimension in data array (%i) must match.' % (coords.shape[0],data.shape[idim])
    newcoords = numpy.empty(data.shape,coords.dtype)
    tp = range(newcoords.ndim)
    tp.append(tp.pop(idim))
    newcoords = newcoords.transpose(tp)
    newcoords[:] = coords
    tp = range(newcoords.ndim)
    tp.insert(idim,tp.pop())
    return newcoords.transpose(tp)

def argtake(data,ind,axis):
    assert data.ndim==ind.ndim or data.ndim==ind.ndim+1, 'Number of dimensions for indices (%i) must be equal to, or one less than number of data dimensions (%i).' % (ind.ndim,data.ndim)
    reduce = (data.ndim==ind.ndim+1)
    allind = []
    for i in range(data.ndim):
        if i==axis:
            allind.append(ind)
        else:
            curind = numpy.empty(ind.shape,ind.dtype)
            idim = i
            if reduce and i>axis: idim-=1
            curind.swapaxes(idim,-1)[:] = numpy.arange(data.shape[i])
            allind.append(curind)
    return data[tuple(allind)]

def getPercentile(data,cumweights,value,axis):
    assert value>=0 and value<=1., 'Percentile value must be between 0 and 1.'
    
    # First get indices where cumulative distribution >= critical value
    #cumweights = numpy.ma.masked_less(cumweights,value)
    cumweights = cumweights.copy()
    cumweights[cumweights<value] = 2.
    
    # Make sure that the cumulative distribution at the highest index still equals one.
    ind = [slice(0,cumweights.shape[i]) for i in range(cumweights.ndim)]
    ind[axis] = -1
    cumweights[tuple(ind)] = 1.
    
    highindices = cumweights.argmin(axis=axis)
    
    # If the high index if the lowest possible (0), increase it with one
    # because the lower index will be one lower.
    numpy.putmask(highindices,highindices==0,1)
    
    # Now get indices where cumulative distribution < critical value
    lowindices = highindices-1
    
    # Do linear interpolation between low and high indices
    highval = argtake(data,highindices,axis)
    lowval  = argtake(data,lowindices,axis)
    highcoords = argtake(cumweights,highindices,axis)
    lowcoords  = argtake(cumweights,lowindices, axis)
    highweight = (value-lowcoords)/(highcoords-lowcoords)
    return highval*highweight + lowval*(1.-highweight)

defaultdimensioninfo = {'label':'','unit':'','preferredaxis':None,'datatype':'float','reversed':False}

def stagger(coords,dimindices=None,defaultdeltafunction=None,dimnames=None):
    if dimindices==None: dimindices = range(coords.ndim)

    # Calculate the shape of the to-be-created staggered array.
    stagshape = list(coords.shape)
    for i in dimindices: stagshape[i] += 1

    # Create one array to hold center values with one index before,
    # and one one index beyong original center coordinates.
    # (interfaces will ultimately be the average of these two)    
    coords_stag  = numpy.zeros(stagshape,coords.dtype)
    coords_stag2 = numpy.zeros(stagshape,coords.dtype)
    
    # Copy center values
    slc1,slc2 = [slice(None)]*coords.ndim,[slice(None)]*coords.ndim
    for i in dimindices:
        slc1[i] = slice(0,-1,  1)
        slc2[i] = slice(1,None,1)
    coords_stag [tuple(slc1)] = coords
    coords_stag2[tuple(slc2)] = coords
    
    # Linearly interpolate center values to get values to append to the
    # front and back
    for idim in dimindices:
        targetslc = [slice(None)]*coords.ndim
    
        # Get values at one index beyond original data
        for inextdim in range(idim+1,coords.ndim):
            if inextdim in dimindices: targetslc[inextdim] = slice(0,-1,1)
        sourceslc1,sourceslc2 = list(targetslc),list(targetslc)
        targetslc[idim],sourceslc1[idim],sourceslc2[idim] = -1,-3,-2
        if coords.shape[idim]==1:
            if defaultdeltafunction==None:
                delta = 1
            else:
                assert dimnames!=None,'If a function supplying default delta is given, the dimension names must be given as well.'
                delta = defaultdeltafunction(dimnames[idim],coords)
        else:
            delta = (coords_stag[tuple(sourceslc2)]-coords_stag[tuple(sourceslc1)])
        coords_stag[tuple(targetslc)] = coords_stag[tuple(sourceslc2)]+delta
        
        # Get values at one index before original data
        for inextdim in range(idim+1,coords.ndim):
            if inextdim in dimindices: targetslc[inextdim] = slice(1,None,1)
        sourceslc1,sourceslc2 = list(targetslc),list(targetslc)
        targetslc[idim],sourceslc1[idim],sourceslc2[idim] = 0,1,2
        if coords.shape[idim]>1:
            delta = (coords_stag2[tuple(sourceslc2)]-coords_stag2[tuple(sourceslc1)])
        coords_stag2[tuple(targetslc)] = coords_stag2[tuple(sourceslc1)]-delta

    return 0.5*(coords_stag+coords_stag2)

def getboundindices(data,axis,minval=None,maxval=None):
    if isinstance(minval,datetime.datetime): minval = date2num(minval)
    if isinstance(maxval,datetime.datetime): maxval = date2num(maxval)
    if data.ndim>1:
        n = data.shape[axis]
        data = data.swapaxes(0,axis).reshape((n,-1))
        if minval!=None: lc = data.max(axis=1)
        if maxval!=None: uc = data.min(axis=1)
    else:
        n,uc,lc = len(data),data,data
    imin,imax = 0,n
    if minval!=None: imin = min(n-1,max(0,lc.searchsorted(minval)))
    if maxval!=None: imax = max(1  ,min(n,uc.searchsorted(maxval)))
    return imin,imax

class VariableStore(UserDict.DictMixin):
    """Abstract base class for objects containing one or more variables that
    can be plotted. It contains functionality for retrieving variable
    short/long names, information on dimensions, and a function that returns
    a hierarchical representation of the variables based on an XML schema.
    """

    def __init__(self):
        self.children = {}
        self.rawlabels = None
        self.newlabels = None
        
    def relabelVariables(self):
        self.rawlabels,self.newlabels = {},{}
        regexp = re.compile('\W')
        for varname in self.getVariableNames_raw():
            newname = regexp.sub('_',varname)
            self.rawlabels[newname] = varname
            self.newlabels[varname] = newname
        
    def addChild(self,child,name=None):
        if name==None and isinstance(child,Variable): name=child.getName_raw()
        assert name!=None,'No name specified, but the child object does not have an internal name either.'
        self.children[name] = child

    def removeChild(self,name):
        assert name in self.children, 'Child %s does not exist in this VariableStore object.' % name
        return self.children.pop(name)

    def removeAllChildren(self):
        self.children = {}
        
    def keys(self):
        """Returns a list of short names for all variables present in the store.
        """
        return self.getVariableNames()

    def __getitem__(self,expression):
        return self.getExpression(expression)
        
    def __contains__(self,varname):
        if self.rawlabels!=None: return varname in self.rawlabels
        return UserDict.DictMixin.__contains__(self,varname)

    def getVariable(self,varname):
        """Returns a Variable object for the given short variable name.
        """
        if varname in self.children:
            child = self.children[varname]
            if isinstance(child,Variable): return child
        rawname = varname
        if self.rawlabels!=None: rawname = self.rawlabels.get(varname,None)
        var = self.getVariable_raw(rawname)
        if var!=None: var.forcedname = varname
        return var
        
    def normalizeExpression(self,expression,defaultchild=None):
        import expressions
        exp = self.getExpression(expression,defaultchild)
        if isinstance(exp,expressions.VariableExpression): return exp.buildExpression()
        return exp.namespacename

    def getExpression(self,expression,defaultchild=None):
        """Returns a Variable object for the given expression, which may contain
        (short) variable names, the normal mathematical operators, and any function
        supported by NumPy.
        """
        # Create the namespace that must be used when then expression is evaluated.
        import expressions
        namespace = expressions.ExpressionNamespace(expressions.LazyStore(self))
        if defaultchild!=None:
            defaultvars = {}
            defaultsource = self.children[defaultchild]
            assert isinstance(defaultsource,VariableStore), 'Default variable source must be of type VariableStore.'
            for varname in defaultsource.getVariableNames():
                var = defaultsource.getVariable(varname)
                lazyvar = expressions.LazyVariable(var)
                lazyvar.name = '%s[\'%s\']' % (defaultchild,varname)
                defaultvars[varname] = lazyvar
            namespace.append(defaultvars)
            
        # Evaluate the expression
        try:
            result = expressions.VariableExpression.resolve(expression,namespace)
        except Exception,e:
            #raise Exception('Unable to resolve expression "%s" to a valid data object. Global table contains: %s. Error: %s' % (expression,', '.join(sorted(namespace.keys())),e))
            raise Exception('Unable to resolve expression "%s" to a valid data object. Error: %s' % (expression,e))
        return result
                
    def getVariableNames(self,alllevels=False):
        """Returns a list of short names for all variables present in the store.
        """
        if self.rawlabels!=None:
            varnames = self.rawlabels.keys()
        else:
            varnames = self.getVariableNames_raw()
        for childname,child in self.children.iteritems():
            if isinstance(child,Variable):
                varnames.append(childname)
            elif alllevels and isinstance(child,VariableStore):
                for vn in child.getVariableNames(alllevels=alllevels):
                    varnames.append('%s[\'%s\']' % (childname,vn))
        return varnames

    def getPlottableVariableNames(self):
        varnames = self.getPlottableVariableNames_raw()
        if self.rawlabels!=None: varnames = [self.newlabels[varname] for varname in varnames]
        for childname,child in self.children.iteritems():
            if isinstance(child,Variable): varnames.append(childname)
        return varnames
        
    def getPlottableVariableNames_raw(self):
        """Returns a list of original short names for all variables that can be plotted.
        Derived classes should implement this method if they want to exclude certain
        variables from being plotted.
        """
        return self.getVariableNames_raw()

    def getVariableLongNames(self,alllevels=False):
        """Returns a dictionary linking variable short names to long names.
        """
        longnames = self.getVariableLongNames_raw()
        if self.rawlabels!=None:
            longnames = dict([(self.newlabels[varname],longname) for (varname,longname) in longnames.iteritems()])
        for childname,child in self.children.iteritems():
            if isinstance(child,Variable):
                longnames[childname] = child.getLongName()
            elif alllevels and isinstance(child,VariableStore):
                for vn,ln in child.getVariableLongNames(alllevels=alllevels).iteritems():
                    longnames['%s[\'%s\']' % (childname,vn)] = ln
        return longnames
        
    def getDimensionInfo(self,dimname):
        if self.rawlabels!=None: dimname = self.rawlabels.get(dimname,dimname)
        return self.getDimensionInfo_raw(dimname)

    def getDimensionInfo_raw(self,dimname):
        """Returns the a dictionary with properties of the specified dimension.
        This includes the label (long name), unit, data type, the preferred axis
        (x or y).
        """
        return dict(defaultdimensioninfo)

    def getVariableTree(self,path,otherstores={},plottableonly=True):
        """Returns a tree representation of the variables in the data store,
        represented by an xmlstore.TypedStore object that uses the short names
        of variables as node names.
        
        The data type of each variable node is boolean, which allows the use of
        the returned object as a basis for a tree with checkboxes for each
        variable (e.g. for selecting variables to include in GOTM-GUI reports).
        
        All variables that are present in the store but not represented by a node
        in the store schema will be added to the node named "other" in the tree,
        if that node is present. Nodes that are present in the schema, but whose
        names does not match the name of a variable, while they also do not contain
        any valid variables will be removed from the tree. The label (= long name)
        of nodes representing a variable will set to the long name of the variable
        as it is known in the variable store if it was not yet set.
        """
        # Get the schema as XML DOM object.
        xmlschema = xml.dom.minidom.parse(path)
        
        # Get dictionary linking variable short names to variable long names.
        # it will be used to check whether a node name matches a variable name,
        # and if so also to fill in the node label with the variable long name.
        vardict = self.getVariableLongNames()
        
        # Remove non-plottable variables
        if plottableonly:
            plottable = self.getPlottableVariableNames()
            for varname in vardict.keys():
                if varname not in plottable: del vardict[varname]
        
        # Prune the tree and fill in node labels where needed.
        found = VariableStore.filterNodes(xmlschema.documentElement,vardict)
        
        # Get a list of variables (short names) that were not present in the schema.
        # We will add these to the schema node "other", if that is present.
        remaining = set(vardict.keys()) - found
        
        # Find the "other" node.
        for other in xmlschema.getElementsByTagName('element'):
            if other.getAttribute('name')=='other': break
        else:
            other = None

        # If the "other" node is present, add the remaining variable if there
        # are any; if there are none, remove the "other" node form the tree.
        if other!=None:
            if len(remaining)==0:
                other.parentNode.removeChild(other)
            else:
                # Sort remaining variables alphabetically on their long names
                for varid in sorted(remaining,cmp=lambda x,y: cmp(vardict[x].lower(), vardict[y].lower())):
                    el = xmlschema.createElement('element')
                    el.setAttribute('name',varid)
                    el.setAttribute('label',vardict[varid])
                    el.setAttribute('type','bool')
                    other.appendChild(el)
                    
        # The XML schema has been pruned and overriden where needed.
        # Return an TypedStore based on it.
        return xmlstore.xmlstore.TypedStore(xmlschema,otherstores=otherstores)

    @staticmethod
    def filterNodes(node,vardict):
        """Takes a node in the schema, and checks whether it and its children
        are present in the supplied dictionary. Nodes not present in the
        dictionary are removed unless they have children that are present in
        the dictionary. This function returns a list of dictionary keys that
        we found in/below the node.
        
        This function is called recursively, and will be used internally only
        by getVariableTree.
        """
        nodeids = set()

        # Get the name of the node.
        nodeid = node.getAttribute('name')
        assert nodeid!='', 'Node lacks "name" attribute.'
        
        # If the name of the node matches a key in the dictionary,
        # fill in its label and data type, and add it to the result.
        if nodeid in vardict:
            if not node.hasAttribute('label'):
                node.setAttribute('label',vardict[nodeid])
            node.setAttribute('type','bool')
            nodeids.add(nodeid)
            
        # Test child nodes and append their results as well.
        for ch in xmlstore.util.findDescendantNodes(node,['element']):
            nodeids |= VariableStore.filterNodes(ch,vardict)
            
        # If the current node and its children did not match a key in the
        # dictionary, remove the current node.
        if len(nodeids)==0 and nodeid!='other':
            node.parentNode.removeChild(node)

        # Return a list of dictionary keys that matched.
        return nodeids

    def getVariable_raw(self,varname):
        """Returns a Variable object for the given original short variable name.
        The method must be implemented by derived classes.
        """
        return None

    def getVariableNames_raw(self):
        """Returns a list of original short names for all variables present in the store.
        The method must be implemented by derived classes.
        """
        return []
                
    def getVariableLongNames_raw(self):
        """Returns a dictionary with original short variable names as keys, long
        variable names as values. This base implementation should be overridden
        by derived classes if it can be done more efficiently.
        """
        return dict([(name,self.getVariable_raw(name).getLongName()) for name in self.getVariableNames_raw()])

class Variable:
    """Abstract class that represents a variable that can be plotted.
    """
    
    class Slice:
        """Object representing a slice of data. It stores the names of
        coordinate dimensions internally, and is also maintains two versions
        of coordinates: one for grid centers and one for grid interfaces.
        
        Currently it can also contain upper and lower confidence boundaries
        for the data values. These objects have the same dimension as the data
        array. Note that this functionality may be relocated in the future.
        """
        def __init__(self,dimensions=(),coords=None,coords_stag=None,data=None):
            self.ndim = len(dimensions)
            if coords     ==None: coords      = self.ndim*[None]
            if coords_stag==None: coords_stag = self.ndim*[None]
            self.dimensions = dimensions
            self.data = data
            self.coords = coords
            self.coords_stag = coords_stag
            
            # Bounds for confidence interval (optional)
            self.lbound = None
            self.ubound = None
        
        def isValid(self):
            """Returns true if the slice if valid, i.e., if dimensions and
            coordinates are properly specified. Note that if a slice is valid,
            it might still be empty.
            """
            return (self.data!=None) and (None not in self.coords) and (None not in self.coords_stag)
            
        def debugCheck(self,context=''):
            if context!='': context += ': '
            assert self.data.ndim==self.ndim, '%snumber of data dimensions (%i) does not match internal number of dimensions (%i).' % (context,self.data.ndim,self.ndim)
            assert len(self.dimensions)==self.ndim, '%snumber of dimension names (%i) does not match internal number of dimensions (%i).' % (context,len(self.dimensions),self.ndim)
            assert self.ndim==len(self.coords), '%snumber of centered coordinate dimensions (%i) does not match internal number of dimensions (%i).' % (context,len(self.coords),self.ndim)
            assert self.ndim==len(self.coords_stag), '%snumber of staggered coordinate dimensions (%i) does not match internal number of dimensions (%i).' % (context,len(self.coords_stag),self.ndim)

        def generateStaggered(self):
            """Creates a vector of interface coordinates from the vector of center
            coordinates.
            """
            for idim in range(self.ndim):
                assert self.coords[idim]!=None, 'Cannot generate staggered coordinates because centered coordinates have not been set.'
                assert self.coords[idim].ndim==1, 'Currently a staggered grid can only be generated automatically for 1D coordinate vectors.'
                self.coords_stag[idim] = getCenters(self.coords[idim],addends=True)
                
        def squeeze(self):
            """Returns the slice with singleton dimensions removed. The singeton
            dimensions are stored as an array of fixed coordinates (with tuples dimension name,
            coordinate value) in the new slice.
            """
            # Find non-singleton dimensions, and store them as fixed extra coordinates.
            gooddimindices,baddimindices = [],[]
            gooddimnames = []
            fixedcoords = []
            for idim,dimname in enumerate(self.dimensions):
                if self.data.shape[idim]>1:
                    # Normal dimension (more than one coordinate)
                    gooddimindices.append(idim)
                    gooddimnames.append(dimname)
                elif self.data.shape[idim]==1:
                    # Singleton dimension
                    baddimindices.append(idim)
                    fixedcoords.append((dimname,self.coords[idim][0]))

            newslice = Variable.Slice(gooddimnames)
            newslice.coords,newslice.coords_stag = [],[]
            for i in gooddimindices:
                coord,coord_stag = self.coords[i],self.coords_stag[i]
                if coord.ndim>1:
                    for j in reversed(baddimindices):
                        coord,coord_stag = coord.mean(axis=j),coord_stag.mean(axis=j)
                newslice.coords.append(coord)
                newslice.coords_stag.append(coord_stag)
            newslice.data = self.data.squeeze()
            newslice.fixedcoords =fixedcoords

            # Update confidence interval (if any)
            if self.lbound!=None: newslice.lbound = self.lbound.squeeze()
            if self.ubound!=None: newslice.ubound = self.ubound.squeeze()

            return newslice
            
        def removeDimension(self,idimension,inplace=True):
            if inplace:
                target = self
            else:
                target = Variable.Slice()
            newcoords,newcoords_stag = [],[]
            for idim in range(len(self.coords)):
                if idim==idimension: continue
                coords = self.coords[idim]
                coords_stag = self.coords_stag[idim]
                if self.coords[idim].ndim>1:
                    # Coordinate array has more than 1 dimensions.
                    # Squeeze out the dimension for which we are calculating statistics.
                    coords = coords.take((0,),idimension)
                    coords_stag = coords_stag.take((0,),idimension)
                    coords.shape = coords.shape[:idimension]+coords.shape[idimension+1:]
                    coords_stag.shape = coords_stag.shape[:idimension]+coords_stag.shape[idimension+1:]
                newcoords.append(coords)
                newcoords_stag.append(coords_stag)
            target.coords = newcoords
            target.coords_stag = newcoords_stag
            target.ndim = self.ndim-1
            newdims = list(self.dimensions)
            del newdims[idimension]
            target.dimensions = tuple(newdims)
            return target
            
        def __getitem__(self,slic):
            # Check whether the slice argument contains only integers and slice objects,
            # and build an array with slices for staggered coordinates.
            assert len(slic)==self.data.ndim, 'Number of slices (%i) does not match number of variable dimensions (%i).' % (len(slic),self.data.ndim)
            
            cslice_stag = []
            for i,s in enumerate(slic):
                assert isinstance(s,(int,slice)),'The slice argument for dimension %s is not an integer or slice object. Fancy indexing with arrays of integers or booleans is not yet supported.' % self.dimensions[i]
                if isinstance(s,slice):
                    start,stop,step = s.indices(self.data.shape[i])
                    assert step==1,'The step argument for slicing dimension %s equals %i. Slices with a step other than 1 are not yet supported.' % (self.dimensions[i],step)
                    cslice_stag.append(slice(start,stop+1))
                else:
                    cslice_stag.append(s)
        
            # Obtain sliced dimensions and coordinates
            dims,coords,coords_stag = [],[],[]
            for i in range(len(self.dimensions)):
                if not isinstance(slic[i],(int,float)):
                    dims.append(self.dimensions[i])
                    if self.coords[i].ndim>1:
                        cur_cslice = slic
                        cur_cslice_stag = cslice_stag
                    else:
                        cur_cslice = slic[i]
                        cur_cslice_stag = cslice_stag[i]
                    coords.append(self.coords[i].__getitem__(cur_cslice))
                    coords_stag.append(self.coords_stag[i].__getitem__(cur_cslice_stag))
            
            # Build and return the new Variable.Slice object
            newslice = Variable.Slice(dims,coords=coords,coords_stag=coords_stag)
            newslice.data = self.data.__getitem__(slic)
            return newslice

    def __init__(self,store):
        self.store = store
        self.forcedname = None
        
    def __getattr__(self,name):
        """Attribute-based access to some variable properties,
        mimicking the Scientific.IO.NetCDF interface.
        """
        if name=='dimensions':
            return self.getDimensions()
        elif name=='unit':
            return self.getUnit()
        elif name=='long_name':
            return self.getLongName()
        elif name=='shape':
            return self.getShape()
        else:
            raise AttributeError(name)

    def getName(self):
        if self.forcedname!=None: return self.forcedname
        return self.getName_raw()

    def getName_raw(self):
        """Returns the short name (or identifier) of the variable.
        This name must be unique within the data store, as it is the key
        that will be used to retrieve data.
        """
        return ''

    def getItemCount(self):
        """Returns the number of data objects within the variable (e.g., when it represents
        a tuple or list.
        """
        return 1

    def getShape(self):
        """Returns the shape of the data array.
        """
        assert False, 'Method "getShape" must be implemented by derived class.'
        
    def hasReversedDimensions(self):
        """Returns whether the order of the variable dimensions is reversed, i.e.,
        the dimension that should be used for the y- axis appears before the dimension
        to be used on the x-axis.
        """
        return False

    def getLongName(self):
        """Returns a long (pretty) name for the variable.
        """
        return ''

    def getUnit(self):
        """Returns the unit of the variable.
        """
        return ''

    def getDimensions(self):
        dims = self.getDimensions_raw()
        if self.store!=None and self.store.newlabels!=None:
            dims = tuple([self.store.newlabels.get(dim,dim) for dim in dims])
        return dims

    def getDimensions_raw(self):
        """Returns the names of the dimensions of the variable as tuple of strings.
        """
        return ()

    def getSlice(self,bounds):
        """Returns a slice from the data. The bounds argument must be a
        list of n tuples, with n being the number of dimensions of the variable
        (as returned by getDimensions). Each tuple must contain a lower- and upper
        boundary of the corresponding dimension. These bounds may be used to
        retrieve a subset of data more efficiently - the Variable is *not*
        required to return only data from within the specified range!
        """
        return self.Slice()

    def getDimensionInfo(self,dimname):
        return self.getDimensionInfo_raw(dimname)

    def getDimensionInfo_raw(self,dimname):
        """Gets information on the specified dimension of the variable.
        See also VariableStore.getDimensionInfo.
        """
        return self.store.getDimensionInfo_raw(dimname)
        
    def copy(self):
        dims = self.getDimensions_raw()
        data = self.getSlice([slice(None)]*len(dims))
        return CustomVariable(data,
                              self.getName_raw(),
                              self.getLongName(),
                              self.getUnit(),
                              dims,
                              dict([(d,self.getDimensionInfo_raw(d)) for d in dims]),
                              self.hasReversedDimensions())
        
class CustomVariable(Variable):
    def __init__(self,slice,name,longname=None,unit='',dimensions=(),dimensioninfo=None,hasreverseddimensions=False):
        Variable.__init__(self,None)
        self.name = name
        self.longname = longname
        self.unit = unit
        self.dimensions = dimensions
        self.dimensioninfo = {}
        if dimensioninfo!=None:
            for d in dimensions: self.dimensioninfo[d] = dimensioninfo[d]
        self.hasreverseddimensions = hasreverseddimensions
        self.slice = slice
        
    def getName_raw(self):
        return self.name
        
    def getLongName(self):
        return self.longname

    def getUnit(self):
        return self.unit

    def getDimensions_raw(self):
        return tuple(self.dimensions)

    def getDimensionInfo_raw(self,dimname):
        if dimname in self.dimensioninfo: return self.dimensioninfo[dimname]
        return dict(defaultdimensioninfo)

    def hasReversedDimensions(self):
        return self.hasreverseddimensions

    def getShape(self):
        return tuple(self.slice.data.shape)

    def getSlice(self,bounds):
        return self.slice
        
class DeferredVariable(Variable):
    def __init__(self,sourcevariable):
        Variable.__init__(self,None)
        self.source = sourcevariable

    def getName_raw(self):
        return self.source.getName_raw()
        
    def getLongName(self):
        return self.source.getLongName()

    def getUnit(self):
        return self.source.getUnit()

    def getDimensions_raw(self):
        return self.source.getDimensions_raw()

    def getDimensionInfo_raw(self,dimname):
        return self.source.getDimensionInfo_raw(dimname)

    def hasReversedDimensions(self):
        return self.source.hasReversedDimensions()

    def getShape(self):
        return self.source.getShape()

    def getSlice(self,bounds):
        return self.source.getSlice(bounds)

class FunctionVariable(DeferredVariable):
    def __init__(self,sourcevariable,dimbounds=None,resolution=100):
        DeferredVariable.__init__(self,sourcevariable)
        if dimbounds==None: dimbounds = {}
        self.dimbounds = dimbounds
        self.resolution = resolution
        self.functions = []
        self.dimtransforms = {}
        self.vectorized = False
        
    def clearFunctions(self):
        self.functions = []

    def addFunction(self,function,condition=None):
        self.functions.append((condition,function))
        
    def setDimensionBounds(self,dimname,minval,maxval):
        self.dimbounds[dimname] = (minval,maxval)
        
    def addDimensionTransform(self,dimname,offset=0.,scale=1.):
        self.dimtransforms[dimname] = (offset,scale)
        
    #def setGrid(self,grid,grid_stag=None):
    #    if grid[0].ndim==1:
    #        if grid_stag==None:
    #            grid_stag = [getCenters(c,addends=True) for c in grid]
    #            grid_stag = ndgrid(*grid_stag)
    #        grid = ndgrid(*grid)
    #    assert grid_stag!=None, 'If grid coordinates are provided as multidimensional arrays, staggered coordinates must be provided explicitly.'
    #    self.grid,self.grid_stag = grid,grid_stag
        
    def setVectorized(self,vectorized=True):
        self.vectorized = vectorized

    def hasReversedDimensions(self):
        return False
        
    def getShape(self):
        assert False, 'getShape is not supported on FunctionVariable objects, because the shape will adapt to requested data ranges.'
        
    def getSlice(self,bounds):
        dimnames = self.getDimensions()
        
        # Build grid
        grid = []
        for d,curbounds in zip(dimnames,bounds):
            curbounds = self.dimbounds.get(d,None)
            assert curbounds!=None, 'Dimension boundaries for %s were not set upon initialization.' % d
            c = numpy.linspace(curbounds[0],curbounds[1],self.resolution)
            grid.append(c)
        grid_stag = [getCenters(c,addends=True) for c in grid]
        grid_stag = ndgrid(*grid_stag)
        grid = ndgrid(*grid)
        
        # Get coordinates with offset+scale transformations applied.
        grid_tf = []
        for d,c in zip(dimnames,grid):
            if d in self.dimtransforms:
                offset,scale = self.dimtransforms[d]
                c = (c-offset)/scale
            grid_tf.append(c)
            
        # Compile conditions and functions
        functions = []
        for condition,function in self.functions:
            function = compile(function,'<string>','eval')
            if condition!=None: condition = compile(condition,'<string>','eval')
            functions.append((condition,function))
            
        # Create empty array for holding data
        data = numpy.empty(grid[0].shape,numpy.float)
        
        # Build base namespace with NumPy functions.
        namespace = dict([(m,getattr(numpy,m)) for m in dir(numpy)])
        
        if self.vectorized:
            # Functions and conditions are vectorized: one evaluation per function/condition
            for d,c in zip(dimnames,grid_tf): namespace[d] = c
            for condition,function in reversed(functions):
                vals = eval(function,namespace)
                if condition==None:
                    data[...] = vals
                else:
                    index = eval(condition,namespace)
                    data[index] = vals[index]
        else:
            # Functions and conditions are not vectorized: one evaluation per grid point, per function
            for index in numpy.ndindex(data.shape):
                for d,c in zip(dimnames,grid_tf): namespace[d] = c[index]
                for condition,function in functions:
                    if condition==None or eval(condition,namespace):
                        data[index] = eval(function,namespace)
                        break
                        
        return Variable.Slice(dimensions=dimnames,coords=grid,coords_stag=grid_stag,data=data)
