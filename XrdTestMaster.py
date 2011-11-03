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
from ClusterManager import ClusterManagerException, loadClustersDefs
from Daemon import Runnable, Daemon, DaemonException, Runnable, Daemon, \
    DaemonException
from Utils import FixedSockStream
from cherrypy.lib.sessions import close
from optparse import OptionParser
from string import join
import ConfigParser
import Queue
import SocketServer
import cherrypy
import datetime
import hashlib
import logging
import os
import signal
import socket
import ssl
import sys
import threading
import time
#-------------------------------------------------------------------------------
# Globals and configurations
#-------------------------------------------------------------------------------
logging.basicConfig(format='%(asctime)s %(levelname)s [%(lineno)d] ' + \
                    '%(message)s', level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)
LOGGER.debug("Running script: " + __file__)

currentDir = os.path.dirname(os.path.abspath(__file__))
defaultConfFile = '/etc/XrdTest/XrdTestMaster.conf'
defaultPidFile = '/var/run/XrdTestMaster.pid'
defaultLogFile = '/var/log/XrdTest/XrdTestMaster.log'
webpageDir = currentDir + os.sep + 'webpage'
defaultClustersDefinitionsPath = '/etc/XrdTest'
cherrypyConfig = {'/webpage/js': {
                     'tools.staticdir.on': True,
                     'tools.staticdir.dir' : webpageDir + "/js",
                     },
                  '/webpage/css': {
                     'tools.staticdir.on': True,
                     'tools.staticdir.dir' : webpageDir + "/css",
                     }
                }

#-------------------------------------------------------------------------------
# The list of connected supervisors
# e.g. list: { client_address : (socket_obj, bin_flag conn_status), }
HIPERVISORS = {}
#-------------------------------------------------------------------------------
# Locking queue with messages from hipervisors
HIPERVISORS_RECV_QUEUE = Queue.Queue()

ACCESS_PASSWORD = hashlib.sha224("tajne123").hexdigest()
SERVER_IP, SERVER_PORT = "127.0.0.1", 20000

#-------------------------------------------------------------------------------
def sendMsg(receiverAddr, msg):
    '''
    Send message to one of the hipervisors by addr
    @param receiverAddr: addr of hipervisor (IP, port) tuple
    @param msg: message to be sent
    '''
    global HIPERVISORS
    if HIPERVISORS.has_key(receiverAddr):
        try:
            LOGGER.debug('Sending: ' + str(msg) + ' to ' + str(receiverAddr))
            if HIPERVISORS[receiverAddr][0]:
                HIPERVISORS[receiverAddr][0].send(msg)

        except socket.error, e:
            LOGGER.exception(e)

    return

#-------------------------------------------------------------------------------
class ThreadedTCPRequestHandler(SocketServer.BaseRequestHandler):
    """
    Client's request handler.
    """
    #---------------------------------------------------------------------------
    def setup(self):
        '''
        Initiate class properties
        '''
        self.stopEvent = threading.Event()
        self.stopEvent.clear()
        self.sockStream = None
    #---------------------------------------------------------------------------
    def socketDisconnected(self):
        '''
        Reaction on socket disconnection.
        '''
        global LOGGER, HIPERVISORS
        LOGGER.debug("@TODO: handle socket disconnected")
        HIPERVISORS[self.client_address][1] = 0
        LOGGER.debug("Someone disconnected. Supervisors list: " + str(HIPERVISORS))
    #---------------------------------------------------------------------------
    def authHipervisor(self):
        '''
        Check if supervisor is authentic
        '''
        msg = self.sockStream.recv()
        LOGGER.info("Received: " + msg)
        LOGGER.info("From: " + str(self.client_address))

        if msg == ACCESS_PASSWORD:
            self.sockStream.send('OK')
        else:
            self.sockStream.send('WRONG PASSWD')
            LOGGER.info("Incoming supervisor connection rejected. " + \
                        "It didn't provide correct password")
    #---------------------------------------------------------------------------
    def registerHipervisor(self):
        '''
        Register in application connected and authenticated supervisor.
        @param client_address:
        @param sockStream:
        '''
        global HIPERVISORS
        HIPERVISORS[self.client_address] = (self.sockStream, 1)
        LOGGER.info("Supervisors list: " + str(HIPERVISORS))
        signal.alarm(5)
        time.sleep(1)
        signal.alarm(0)
    #---------------------------------------------------------------------------
    def handle(self):
        '''
        Handle new incoming connection and keep it to receive messages.
        '''
        global LOGGER, ACCESS_PASSWORD, HIPERVISORS_RECV_QUEUE, currentDir

        self.sockStream = ssl.wrap_socket(self.request, server_side=True,
                                          certfile=\
                                         currentDir + '/certs/master/mastercert.pem',
                                          keyfile=\
                                         currentDir + '/certs/master/masterkey.pem',
                                          ssl_version=ssl.PROTOCOL_TLSv1)
        self.sockStream = FixedSockStream(self.sockStream)

        self.authHipervisor()
        self.registerHipervisor()

        while not self.stopEvent.isSet():
            try:
                msg = self.sockStream.recv()
                HIPERVISORS_RECV_QUEUE.put((self.client_address, msg))

                sendMsg(self.client_address, "Response to" + \
                str(self.client_address))
            except socket.error, e:
                self.socketDisconnected()
                LOGGER.exception(e)

        LOGGER.info("SERVER: Closing %s" % (threading.currentThread()))
        self.stopEvent.clear()
        return

class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    pass

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

    LOGGER.info("Reading config file % s", confFile)

    config = ConfigParser.ConfigParser()
    if os.path.exists(confFile):
        try:
            fp = file(confFile, 'r')
            config.readfp(fp)
            fp.close()
        except IOError, e:
            LOGGER.exception()
    else:
        raise XrdTestMasterException("Config file could not be read")
    return config
#------------------------------------------------------------------------------
class WebInterface:
    '''
    Provides web interface for the manager.
    '''
    def index(self):
        global webpageDir, HIPERVISORS
        tplFile = webpageDir + os.sep + 'main.tmpl'
        LOGGER.info(tplFile)

        global currentDir
        clustersList = loadClustersDefs(currentDir + "/clusters")

        tplVars = { 'title' : 'Xrd Test Master - Web Iface',
                    'message' : 'Welcome and begin the tests!',
                    'clusters' : clustersList, 'hipervisors': HIPERVISORS}

        tpl = Template (file=tplFile, searchList=[tplVars])
        return tpl.respond()

    index.exposed = True
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
        global cherrypy, currentDir, cherrypyConfig
        
        server = ThreadedTCPServer((SERVER_IP, SERVER_PORT),
                           ThreadedTCPRequestHandler)
        ip, port = server.server_address
        LOGGER.info("TCP Hipervisor server running " + str(ip) + " " + str(port))
        
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()

        cherrypy.tree.mount(WebInterface(), "/", cherrypyConfig)
        cherrypy.config.update({'server.socket_host': '0.0.0.0',
                            'server.socket_port': 8080,})
        cherrypy.server.start()
        while True:
            time.sleep(30)
            LOGGER.info("Hello everybody!")
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
        LOGGER.info("Loading config file: %s" % options.configFile)
        try:
            config = readConfig(options.configFile)
            isConfigFileRead = True
        except (RuntimeError, ValueError, IOError), e:
            LOGGER.exception()
            sys.exit(1)

    testMaster = XrdTestMaster()
    #--------------------------------------------------------------------------
    # run the daemon
    #--------------------------------------------------------------------------
    if options.backgroundMode:
        LOGGER.info("Run in background: %s" % options.backgroundMode)

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
            LOGGER.exception('')
            sys.exit(1)
    #--------------------------------------------------------------------------
    # run test master in standard mode. Used for debugging
    #--------------------------------------------------------------------------
    if not options.backgroundMode:
        testMaster.run()

def sigAlarmHandler(signum, frame):
    if signum == 5:
        cherrypy.server.restart()

signal.signal(signal.SIGALRM, sigAlarmHandler)
#-------------------------------------------------------------------------------
# Start place
#-------------------------------------------------------------------------------
if __name__ == '__main__':
    main()

