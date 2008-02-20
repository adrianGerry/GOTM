# Import modules from standard Python library
import os, xml.dom.minidom, shutil

# Import own custom modules
import xmlstore.util, xmlstore.xmlstore, xmlplot.plot

def createtable(xmldocument,tds,columncount):
    table = xmldocument.createElement('table')
    icurvar = 0
    tr = None
    for td in tds:
        if icurvar % columncount == 0:
            tr = xmldocument.createElement('tr')
            table.appendChild(tr)
        tr.appendChild(td)
        icurvar = icurvar+1
    if tr!=None and len(table.childNodes)>1:
        for i in range(columncount - len(tr.childNodes)):
            tr.appendChild(xmldocument.createElement('td'))
    return table

class Report(xmlstore.util.referencedobject):
    reportdirname = 'reporttemplates'
    reportname2path = None

    @staticmethod
    def getTemplates():
        if Report.reportname2path==None:
            Report.reportname2path = {}
            sourcedir = Report.reportdirname
            if os.path.isdir(sourcedir):
                for filename in os.listdir(sourcedir):
                    if filename=='CVS': continue
                    fullpath = os.path.join(sourcedir,filename)
                    if os.path.isdir(fullpath):
                        if os.path.isfile(os.path.join(fullpath,'index.xml')):
                            Report.reportname2path[filename] = fullpath
                        else:
                            print 'WARNING: template directory "%s" does not contain "index.xml"; it will be ignored.' % fullpath
                    else:
                        print 'WARNING: template directory "%s" contains "%s" which is not a directory; the latter will be ignored.' % (sourcedir,filename)
            else:
                print 'WARNING: no report templates will be available, because subdirectory "%s" is not present!' % Report.reportdirname
        return Report.reportname2path

    def __init__(self,defaultfont=None):
        xmlstore.util.referencedobject.__init__(self)
        
        self.store = xmlstore.xmlstore.TypedStore('schemas/report/gotmgui.xml')

        self.defaultstore = xmlstore.xmlstore.TypedStore('schemas/report/gotmgui.xml')

        # Set some default properties.
        self.defaultstore['Figures/Width'      ].setValue(10)
        self.defaultstore['Figures/Height'     ].setValue(8)
        self.defaultstore['Figures/Resolution' ].setValue(96)
        self.defaultstore['Figures/FontScaling'].setValue(100)
        self.defaultstore['Figures/FontName'   ].setValue(defaultfont)

        self.store.setDefaultStore(self.defaultstore)
        
    def unlink(self):
        self.defaultstore.release()
        self.defaultstore = None
        self.store.release()
        self.store = None
        
    def generate(self,result,outputpath,templatepath,columncount=2,callback=None):
        xmldocument = xml.dom.minidom.parse(os.path.join(templatepath,'index.xml'))
        scenario = result.scenario
        
        # Get report settings
        figuresize  = (self.store['Figures/Width'     ].getValue(usedefault=True),self.store['Figures/Height'].getValue(usedefault=True))
        dpi         = self.store['Figures/Resolution' ].getValue(usedefault=True)
        fontscaling = self.store['Figures/FontScaling'].getValue(usedefault=True)
        fontname    = self.store['Figures/FontName'   ].getValue(usedefault=True)

        # Get list of variables to plot
        selroot = self.store['Figures/Selection']
        plotvariables = [node.getValue() for node in selroot.children]

        steps = float(2+len(plotvariables))
        istep = 0

        # Get a list of all input datasets.
        inputdata = []
        for node in scenario.root.getNodesByType('gotmdatafile'):
            if node.isHidden(): continue
            value = node.getValue(usedefault=True)
            if value!=None and value.validate():
                inputdata.append((node,value))
                steps += 1+len(value.getVariableNames())

        # Create output directory if it does not exist yet.
        if not os.path.isdir(outputpath): os.mkdir(outputpath)

        # Copy auxilliary files such as CSS, JS (everything but index.xml)
        for f in os.listdir(templatepath):
            fullpath = os.path.join(templatepath,f)
            if f.lower()!='index.xml' and os.path.isfile(fullpath):
                shutil.copy(fullpath,os.path.join(outputpath,f))

        # --------------------------------------------------------------
        # Replace "gotm:scenarioproperty" tags in index.xml by the
        # current value of the corresponding scenario property.
        # --------------------------------------------------------------

        for node in xmldocument.getElementsByTagName('gotm:scenarioproperty'):
            variablepath = node.getAttribute('variable')
            assert variablepath!='', 'gotm:scenarioproperty node in report template lacks "variable" attribute, whcih should point to a location in the scenario.'
            variablenode = scenario[variablepath]
            assert variablenode!=None, 'Unable to locate "%s" in the scenario.' % variablepath
            val = variablenode.getValueAsString()
            node.parentNode.replaceChild(xmldocument.createTextNode(unicode(val)),node)
            node.unlink()

        # --------------------------------------------------------------
        # Build table with scenario settings.
        # --------------------------------------------------------------

        scenarionodes = xmldocument.getElementsByTagName('gotm:scenario')
        assert len(scenarionodes)<=1, 'Found more than one "gotm:scenario" node in the report template.'
        if len(scenarionodes)>0:
            if callback!=None: callback(istep/steps,'Creating scenario description...')
            scenarionode = scenarionodes[0]

            sceninterface = scenario.getInterface(showhidden=False,omitgroupers=True)

            scentable = xmldocument.createElement('table')
            scentable.setAttribute('id','tableScenario')

            totaldepth = sceninterface.getDepth(scenario.root)

            # Create columns.
            for i in range(totaldepth-2):
                col = xmldocument.createElement('col')
                col.setAttribute('width','25')
                scentable.appendChild(col)
            col = xmldocument.createElement('col')
            scentable.appendChild(col)
            col = xmldocument.createElement('col')
            scentable.appendChild(col)

            # Create rows
            for tr in sceninterface.toHtml(scenario.root,xmldocument,totaldepth-1,level=-1,hidedefaults=True):
                scentable.appendChild(tr)
            
            # Break link from scenario to interface.
            scenario.disconnectInterface(sceninterface)
            sceninterface = None

            scenarionode.parentNode.replaceChild(scentable,scenarionode)

        istep += 1
        
        # Create figure to be used for plotting observations and results.
        if len(inputdata)>0 or len(plotvariables)>0:
            fig = xmlplot.plot.Figure(defaultfont=fontname)
        else:
            fig = None
        
        # --------------------------------------------------------------
        # Create figures for input data
        # --------------------------------------------------------------

        if len(inputdata)>0:
            nodeParent = scentable.parentNode
            nodePreceding = scentable.nextSibling
            mintime,maxtime = scenario['/time/start'].getValue(usedefault=True),scenario['/time/stop'].getValue(usedefault=True)
            for node,store in inputdata:
                if callback!=None:
                    store.getData(callback=lambda progress,msg: callback((istep+progress)/steps,'Parsing %s...' % (node.getText(1),)))
                else:
                    store.getData()
                istep += 1
                tds = []
                fig.addDataSource('input',store)
                vardict = store.getVariableLongNames()
                for varid in store.getVariableNames():
                    longname = vardict[varid]
                    if callback!=None: callback(istep/steps,'Creating figure for %s...' % longname)

                    fig.setUpdating(False)
                    fig.clearProperties()
                    fig.addVariable(varid)
                    fig.properties['FontScaling'].setValue(fontscaling)
                    fig.setUpdating(True)
                    
                    fig.setUpdating(False)
                    for axisnode in fig.properties['Axes'].getLocationMultiple(['Axis']):
                        if axisnode['IsTimeAxis'].getValue(usedefault=True):
                            axisnode['MinimumTime'].setValue(mintime)
                            axisnode['MaximumTime'].setValue(maxtime)
                    fig.setUpdating(True)
                    
                    filename = 'in_'+varid+'.png'
                    outputfile = os.path.join(outputpath,filename)
                    fig.exportToFile(outputfile,dpi=dpi)

                    img = xmldocument.createElement('img')
                    img.setAttribute('src',filename)
                    img.setAttribute('alt',longname)
                    img.setAttribute('style','width:%.2fcm' % figuresize[0])
                    td = xmldocument.createElement('td')
                    td.appendChild(img)
                    tds.append(td)

                    istep += 1
                header = xmldocument.createElement('h3')
                header.appendChild(xmldocument.createTextNode(node.getText(1)))
                figurestable = createtable(xmldocument,tds,columncount)
                nodeParent.insertBefore(header,nodePreceding)
                nodeParent.insertBefore(figurestable,nodePreceding)
                
                store.release()
        inputdata = None

        # --------------------------------------------------------------
        # Create figures for result variables
        # --------------------------------------------------------------

        figuresnodes = xmldocument.getElementsByTagName('gotm:figures')
        assert len(figuresnodes)<=1, 'Found more than one "gotm:figures" node in the report template.'
        if len(figuresnodes)>0:
            figuresnode = figuresnodes[0]
        else:
            figuresnode = None
        if len(plotvariables)>0 and figuresnode!=None:
            fig.clearSources()
            fig.addDataSource('result',result)
            tds = []
            for varpath in plotvariables:
                varid = varpath.split('/')[-1]
                
                longname = result.getVariable(varid).getLongName()
                if callback!=None: callback(istep/steps,'Creating figure for %s...' % longname)
                
                fig.setUpdating(False)
                if not result.getFigure('result/'+varpath,fig.properties):
                    fig.clearProperties()
                    fig.addVariable(varid)
                fig.properties['FontScaling'].setValue(fontscaling)
                fig.setUpdating(True)
                filename = 'out_'+varid+'.png'
                outputfile = os.path.join(outputpath,filename)
                fig.exportToFile(outputfile,dpi=dpi)

                img = xmldocument.createElement('img')
                img.setAttribute('src',filename)
                img.setAttribute('alt',longname)
                img.setAttribute('style','width:%.2fcm' % figuresize[0])
                td = xmldocument.createElement('td')
                td.appendChild(img)
                tds.append(td)

                istep += 1
            figurestable = createtable(xmldocument,tds,columncount)
            figuresnode.parentNode.replaceChild(figurestable,figuresnode)
        elif figuresnode!=None:
            figuresnode.parentNode.removeChild(figuresnode)
            
        # Clean-up figure
        if fig!=None: fig.release()
        
        if callback!=None: callback(istep/steps,'Writing HTML...')

        if outputpath!='':
            import codecs
            f = codecs.open(os.path.join(outputpath,'index.html'),'w','utf-8')
            xmldocument.writexml(f,encoding='utf-8')
            f.close()
        else:
            print xmldocument.toxml('utf-8')
        istep += 1

        if callback!=None: callback(istep/steps,'Done.')
