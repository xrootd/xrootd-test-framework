#!/usr/bin/env python
#-------------------------------------------------------------------------------
# Author:  Lukasz Trzaska <ltrzaska@cern.ch>
# Date:    
# File:    XrdTestMaster
# Desc:    Xroot Test managing programme
#-------------------------------------------------------------------------------
# Imports
#-------------------------------------------------------------------------------
from Cheetah.Template import Template
from ClusterManager import ClusterManagerException
from Daemon import Runnable, Daemon, DaemonException, Runnable, Daemon, \
    DaemonException
from cherrypy.lib.sessions import close
from optparse import OptionParser
from string import join
import ConfigParser
import cherrypy
import datetime
import logging
import os
import sys
import time
#-------------------------------------------------------------------------------
# Globals definitions
#-------------------------------------------------------------------------------
logging.basicConfig(format='%(asctime)s %(levelname)s [%(lineno)d] ' + \
                    '%(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
logger.debug("Running script: " + __file__)

cherrypy.config.update({'server.socket_host': '0.0.0.0',
                      'server.socket_port': 8080})

defaultConfFile = '/etc/XrdTest/XrdTestMaster.conf'
defaultPidFile = '/var/run/XrdTestMaster.pid'
defaultLogFile = '/var/log/XrdTest/XrdTestMaster.log'
webpageDir = os.path.dirname(os.path.abspath(__file__)) + os.sep + 'webpage'
defaultClustersDefinitionsPath = '/etc/XrdTest'
#------------------------------------------------------------------------------
class WebInterface:
    '''
    Provides web interface for the manager.
    '''
    def index(self):
        global webpageDir
        tplFile = webpageDir + os.sep + 'main.tmpl'
        logger.info(tplFile)
        tplVars = { 'title' : 'Xrd Test Master - Web Iface',
                    'message' : 'Welcome and begin the tests!'}

        tpl = Template (file=tplFile, searchList=[tplVars])
        return tpl.respond()

    index.exposed = True
#-------------------------------------------------------------------------------
class XrdTestMaster(Runnable):
    '''
    Runnable class, doing XrdTestMaster jobs.
    '''
    #---------------------------------------------------------------------------
    def loadClustersDefs(self, path=None):
        '''
        Loads cluster definitions from .py files stored in path directory
        @param path: path for .py files, storing cluster definitions
        '''

        if not path:
            global defaultClustersDefinitionsPath
            path = defaultClustersDefinitionsPath

        clusters = []
        if os.path.exists(path):
            for f in os.listdir(path):
                fp = path + os.sep + f
                (modPath, modFile) = os.path.split(fp)
                modPath = os.path.abspath(modPath)
                (modName, ext) = os.path.splitext(modFile)

                if os.path.isfile(fp) and ext == '.py':
                    mod = None
                    cl = None
                    try:
                        if not modPath in sys.path:
                            sys.path.insert(0, modPath)

                        mod = __import__(modName, {}, {}, ['getCluster'])
                        cl = mod.getCluster()
                        #after load, check if cluster definition is correct
                        cl.validate()
                        clusters.append(cl)
                    except AttributeError:
                            logger.exception('')
                            raise ClusterManagerException("Method getCluster " + \
                                  "can't be found in " + \
                                  "file: " + str(modFile))
                    except ImportError:
                        logger.exception('')
    #---------------------------------------------------------------------------
    def run(self):
        '''
        Main jobs of programme. Has to be implemented.
        '''


        cherrypy.quickstart(WebInterface()) #@UndefinedVariable
        while True:
            time.sleep(30)
            logger.info("Hello everybody!")
#-------------------------------------------------------------------------------
class XrdTestMasterException(Exception):
    '''
    General Exception raised by Daemon.
    '''
    #---------------------------------------------------------------------------
    def __init__(self, desc):
        '''
        Constructs Exception
        @param desc: description of an error
        '''
        self.desc = desc
    #---------------------------------------------------------------------------
    def __str__(self):
        '''
        Returns textual representation of an error
        '''
        return repr(self.desc)
#-------------------------------------------------------------------------------
def readConfig(optsConfFile=None):
    '''
    Reads configuration from given file or from default if None given.
    @param optsConfFile: file with configuration
    '''
    global defaultConfFile
    confFile = defaultConfFile

    if optsConfFile and os.path.exists(optsConfFile):
        confFile = optsConfFile

    logger.info("Reading config file % s", confFile)

    config = ConfigParser.ConfigParser()
    if os.path.exists(confFile):
        try:
            fp = file(confFile, 'r')
            config.readfp(fp)
            fp.close()
        except IOError, e:
            logger.exception()
    else:
        raise XrdTestMasterException("Config file could not be read")
    return config
#-------------------------------------------------------------------------------
def main():
    '''
    Program begins here.
    '''
    parse = OptionParser()
    parse.add_option("-c", "--configfile", dest="configFile", type="string", \
                     action="store", help="config (.conf) file location")
    parse.add_option("-b", "--background", dest="backgroundMode", \
                     type="string", action="store", \
                      help="run runnable as a daemon")

    (options, args) = parse.parse_args()

    isConfigFileRead = False
    config = ConfigParser.ConfigParser()
    #--------------------------------------------------------------------------
    # read the config file
    #--------------------------------------------------------------------------
    if options.configFile:
        logger.info("Loading config file: %s" % options.configFile)
        try:
            config = readConfig(options.configFile)
            isConfigFileRead = True
        except (RuntimeError, ValueError, IOError), e:
            logger.exception()
            sys.exit(1)

    testMaster = XrdTestMaster()
    #--------------------------------------------------------------------------
    # run the daemon
    #--------------------------------------------------------------------------
    if options.backgroundMode:
        logger.info("Run in background: %s" % options.backgroundMode)

        pidFile = defaultPidFile
        logFile = defaultLogFile
        if isConfigFileRead:
            pidFile = config.get('daemon', 'pid_file_path')
            logFile = config.get('daemon', 'log_file_path')

        dm = Daemon("XrdTestMaster.py", pidFile, logFile)
        try:
            if options.backgroundMode == 'start':
                dm.start(testMaster)
            elif options.backgroundMode == 'stop':
                dm.stop()
            elif options.backgroundMode == 'check':
                res = dm.check()
                print 'Result of runnable check: %s' % str(res)
            elif options.backgroundMode == 'reload':
                dm.reload()
                print 'You can either start, stop, check or reload the deamon'
                sys.exit(3)
        except (DaemonException, RuntimeError, ValueError, IOError), e:
            logger.exception('')
            sys.exit(1)
    #--------------------------------------------------------------------------
    # run test master in standard mode. Used for debugging
    #--------------------------------------------------------------------------
    if not options.backgroundMode:
        testMaster.run()
#-------------------------------------------------------------------------------
# Start place
#-------------------------------------------------------------------------------
if __name__ == '__main__':
    main()

