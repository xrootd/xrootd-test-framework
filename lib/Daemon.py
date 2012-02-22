#!/usr/bin/env python
#-------------------------------------------------------------------------------
# Author:  Lukasz Trzaska <ltrzaska@cern.ch>
# Date:    
# File:    daemonWrapper
# Desc:    TODO
#-------------------------------------------------------------------------------

#-------------------------------------------------------------------------------
# Imports
#-------------------------------------------------------------------------------
from optparse import OptionParser
import ConfigParser
import datetime
import logging
import os
import signal
import sys
import time
#-------------------------------------------------------------------------------
# Globals definitions
#-------------------------------------------------------------------------------
logging.basicConfig(format='%(asctime)s %(levelname)s [%(lineno)d] %(message)s',
                     level=logging.INFO)
LOGGER = logging.getLogger(__name__)
LOGGER.debug("Running script: " + __file__)
#-------------------------------------------------------------------------------
class DaemonException(Exception):
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
        return str(self.desc)
#-------------------------------------------------------------------------------
def readConfig(confFile):
    '''
    Reads configuration from given file or from default if None given.
    @param optsConfFile: file with configuration
    '''
    LOGGER.info("Reading config file % s", str(confFile))

    config = ConfigParser.ConfigParser()
    if os.path.exists(confFile):
        try:
            fp = file(confFile, 'r')
            config.readfp(fp)
            fp.close()
        except IOError, e:
            LOGGER.exception(e)
    else:
        raise DaemonException("Config file could not be read")
    return config
#-------------------------------------------------------------------------------
class Runnable(object):
    '''
    Abstract basic class for object to be runned as a daemon.
    @note: children class it should handle SIGUP signal or it will suspend
    '''
    #---------------------------------------------------------------------------
    def run(self):
        '''
        Main jobs of programme. Has to be implemented.
        '''
        raise NotImplementedError
#-------------------------------------------------------------------------------
class Daemon:
    '''
    Represents and manages running daemon of a given runnable object.
    For initialization it requires object that inherits class Runnable.
    '''
    #---------------------------------------------------------------------------
    # Class properties
    #---------------------------------------------------------------------------
    isDaemon = False
    pidFile = None
    logFile = None
    #---------------------------------------------------------------------------
    def __init__(self, progName, pidFile, logFile):
        '''
        Initiate Daemon managing object.
        Required arguments are: pidFile and logFile.
        @param pidFile: path to file where pid will be stored
        @param logFile: path to file where logs of process will be stored
        @param daemonProgName: progName that will be runned as python argument
        '''
        self.isDaemon = False

        self.progName = progName
        self.pidFile = pidFile
        self.logFile = logFile

        if not self.pidFile or not self.logFile:
            raise DaemonException("No pidfile or logfile provided, unable" +
                                  + " to init Daemon.")
    #---------------------------------------------------------------------------
    def redirectOutput(self):
        '''
        Redirect the stderr and stdout to a file
        '''
        outLog = file(self.logFile, 'a+')
        sys.stdout.flush()
        sys.stderr.flush()
        os.close(sys.stdout.fileno())
        os.close(sys.stderr.fileno())

        os.dup2(outLog.fileno(), sys.stdout.fileno())
        os.dup2(outLog.fileno(), sys.stderr.fileno())
    #---------------------------------------------------------------------------
    def check(self, pid=None):
        '''
        Checks if process with given pid is currently running.
        If no pid is given, it tries to retrieve pid from the pidFile given in
        the constructor of this class.
        @param pid: pid of process to be checked
        @return: pid (if process runs), None (otherwise)
        '''
        global LOGGER

        if pid is None:
            #Try to retrieve pid from pid file given in runnable configuration
            if os.path.exists(self.pidFile):
                try:
                    f = file(self.pidFile, 'r')
                    line = f.readline()
                    pid = int(line)
                except IOError, ValueError:
                    raise RuntimeError("Cannot read pid from a pidfile")
            else:
                #no pid file exists - assume the process doesn't work
                return False

        #pid is obligatory for checking if process is running
        if pid is None:
            raise RuntimeError('No pid of the runnable to be checked given')

        isRunning = False
        if os.path.exists('/proc/' + str(pid)):
            path = '/proc/' + str(pid) + '/cmdline'
            if os.path.exists(path):
                try:
                    f = file(path, 'r')
                    line = f.readline()
                    if self.progName in line:
                        isRunning = True
                except IOError, ValueError:
                    raise RuntimeError("Cannot read " + path)
        if isRunning:
            return pid
        else:
            self.removePidFile()
            return None
        #@todo: sprawdzic nazwe czy ja to ja
    #---------------------------------------------------------------------------
    # Reloads the daemon by sending SIGHUM
    #---------------------------------------------------------------------------
    def reload(self, pid=None):
        global LOGGER
        pid = self.check(pid)
        if not pid:
            raise RuntimeError("Can not realod - daemon not running.")
        else:
            try:
                os.kill(pid, signal.SIGHUP)
            except OSError, e:
                raise RuntimeError('Unable to reload: ' + str(pid)
                                   + ', because: ' + str(e))
            LOGGER.info("Sighup sent to pid: " + str(pid))

    #---------------------------------------------------------------------------
    def start(self, runnable):
        '''
        Starts the daemon as a separate process.
        @param runnable: instance of runnable object (inherits Runnable).
        '''
        global LOGGER
        #@todo: if iscallable runnable czy moge zawolac metode
        if not callable(runnable.run):
            raise RuntimeError("Not a runnable object given to " +
                                   "start the daemon")
        #-----------------------------------------------------------------------
        # Check if the process is already running
        #-----------------------------------------------------------------------
        pid = self.check()
        if pid:
            raise RuntimeError('The process is running, pid: ' + str(pid))
            return
        #-----------------------------------------------------------------------
        # Check if we can access the files
        #-----------------------------------------------------------------------
        try:
            logFile = file(self.logFile, 'a+')
            logFile.close()
            pidFile = file(self.pidFile, 'w')
        except Exception, e:
            raise DaemonException(('Cannot access log file or pid file: ' + \
                                  '%s or %s') % (self.logFile, self.pidFile))
        #-----------------------------------------------------------------------
        # Fork - create daemon process
        #-----------------------------------------------------------------------
        try:
            pid = os.fork()
            if pid > 0:
                #I am the parent
                self.isDaemon = False
                pidFile.close()
                sys.exit(0)
            else:
                os.setsid()
                pid = os.fork()
                if pid > 0:
                    #write a pid to a file and leave the method
                    pidFile.write(str(pid) + " ")
                    LOGGER.info('A daemon with pidfile ' + self.pidFile +
                                ' launched successfully, pid:' + str(pid))
                    self.isDaemon = False
                    pidFile.close()
                    return
                else:
                    #i'm child of a child - the daemon process, so continue
                    self.isDaemon = True
                    pidFile.close()
        except OSError, e:
            raise RuntimeError('Fork for runnable with pidfile ' +
                               self.pidFile + ' failed: ' + str(e))
        #-----------------------------------------------------------------------
        # Redirect the standard input and output of the daemon
        #-----------------------------------------------------------------------
        try:
            devNull = file(os.devnull, 'r')
            os.close(sys.stdin.fileno())
            os.dup2(devNull.fileno(), sys.stdin.fileno())
            os.chdir('/')
            self.redirectOutput()
        except IOError, e:
            raise DaemonException('Cannot redirect output to the log file: ' +
                                  str(e))

        LOGGER.info('Running process with pidfile: ' + self.pidFile +
                    ' [' + str(os.getpid()) + ']')
        sys.stdout.flush()
        #run the daemon tasks
        runnable.run()
    #---------------------------------------------------------------------------
    def stop(self, pid=None):
        '''
        Stop the deamon
        '''
        global LOGGER
        #-----------------------------------------------------------------------
        # Check if the daemon is running
        #-----------------------------------------------------------------------
        pid = self.check(pid)
        if not pid:
            LOGGER.info("The process already stopped")
            return

        try:
            os.kill(pid, signal.SIGTERM)
        except OSError, e:
            raise RuntimeError('Unable to terminate: ' + str(pid) +
                               ', because: ' + str(e))

        self.removePidFile()
    #---------------------------------------------------------------------------
    def removePidFile(self):
        '''
        Remove pid file if it exists
        '''
        if os.path.exists(self.pidFile):
            try:
                os.remove(self.pidFile)
            except:
                LOGGER.error("Cannot delete pidfile")
