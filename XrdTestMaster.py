#!/usr/bin/env python
#-------------------------------------------------------------------------------
# Author:  Lukasz Trzaska <ltrzaska@cern.ch>
# Date:    
# File:    XrdTestMaster
# Desc:    Xroot Test managing programme
#-------------------------------------------------------------------------------
# Imports
#-------------------------------------------------------------------------------
from Daemon import Runnable, Daemon, DaemonException, Runnable, Daemon, \
    DaemonException
from optparse import OptionParser
import ConfigParser
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

defaultConfFile = '/etc/XrdTest/XrdTestMaster.conf'
defaultPidFile = '/var/run/XrdTestMaster.pid'
defaultLogFile = '/var/log/XrdTest/XrdTestMaster.log'
#-------------------------------------------------------------------------------
class XrdTestMaster(Runnable):
    '''
    Runnable class, doing XrdTestMaster jobs.
    '''
    #---------------------------------------------------------------------------
    def run(self):
        '''
        Main jobs of programme. Has to be implemented.
        '''
        while True:
            time.sleep(3)
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
    global defaultConfFile
    confFile = defaultConfFile

    if optsConfFile and os.path.exists(optsConfFile):
        confFile = optsConfFile

    config = ConfigParser.ConfigParser()
    if os.path.exists(confFile):
        try:
            config.readfp(confFile)
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
    parse.add_option("-d", "--debug", dest="debugMode", action="store_true", \
                     help="provide the debug information to the output")

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
    #--------------------------------------------------------------------------
    # run the daemon
    #--------------------------------------------------------------------------
    if options.backgroundMode:
        logger.info("Run in background: %s" % options.backgroundMode)

        pidFile = defaultPidFile
        logFile = defaultLogFile
        if isConfigFileRead:
            pidFile = config.read('daemon', 'pid_file_path')
            logFile = config.read('daemon', 'log_file_path')

        testMaster = XrdTestMaster()

        dm = Daemon("XrdTestMaster.py", "/var/run/XrdTestMaster.pid", \
                    "/var/log/XrdTestMaster.log")

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

#-------------------------------------------------------------------------------
# Start place
#-------------------------------------------------------------------------------
if __name__ == '__main__':
    main()


