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
    DaemonException, readConfig
from SocketUtils import FixedSockStream, SocketDisconnected, XrdMessage, \
    PriorityBlockingQueue
from cherrypy.lib.sessions import close
from optparse import OptionParser
from string import join
import ConfigParser
import Queue
import SocketServer
import cherrypy
import copy
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
                    '%(message)s', level=logging.INFO)
LOGGER = logging.getLogger(__name__)
LOGGER.debug("Running script: " + __file__)

currentDir = os.path.dirname(os.path.abspath(__file__))
#Default daemon configuration
defaultConfFile = './XrdTestMaster.conf'
defaultPidFile = '/var/run/XrdTestMaster.pid'
defaultLogFile = '/var/log/XrdTest/XrdTestMaster.log'
#-------------------------------------------------------------------------------
class InMsg(object):
    '''
    The message incoming to XrdTestMaster. May be either the event e.g.
    hypervisor connection or normal message containing data.
    '''
    PRIO_NORMAL = 9
    PRIO_IMPORTANT = 1

    MSG_DATA = 1
    MSG_HYPERV_CONNECTED = 2
    MSG_HYPERV_DISCONNECTED = 3

    type = MSG_DATA
    data = ''

    def __init__(self, msg_type, msg_data):
        self.type = msg_type
        self.data = msg_data

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
    def authHipervisor(self):
        '''
        Check if hypervisor is authentic
        '''
        msg = self.sockStream.recv()
        LOGGER.info("Received from: " + str(self.client_address) + \
                     " msg: " + str(msg))

        if msg == ACCESS_PASSWORD:
            self.sockStream.send('PASSWD_OK')
        else:
            self.sockStream.send('PASSWD_WRONG')
            LOGGER.info("Incoming hypervisor connection rejected. " + \
                        "It didn't provide correct password")
    #---------------------------------------------------------------------------
    def handle(self):
        '''
        Handle new incoming connection and keep it to receive messages.
        '''
        global LOGGER, ACCESS_PASSWORD, currentDir

        self.sockStream = ssl.wrap_socket(self.request, server_side=True,
                                          certfile=\
                                         currentDir + '/certs/master/mastercert.pem',
                                          keyfile=\
                                         currentDir + '/certs/master/masterkey.pem',
                                          ssl_version=ssl.PROTOCOL_TLSv1)
        self.sockStream = FixedSockStream(self.sockStream)

        self.authHipervisor()
        inMsg = InMsg(InMsg.MSG_HYPERV_CONNECTED,
                      (self.client_address, self.sockStream))
        self.server.hypervRecvQueue.put((InMsg.PRIO_IMPORTANT, inMsg))

        while not self.stopEvent.isSet():
            try:
                msg = self.sockStream.recv()
                inMsg = InMsg(InMsg.MSG_DATA, (self.client_address, msg))
                self.server.testMaster.hypervRecvQueue\
                .put((InMsg.PRIO_NORMAL, inMsg))
            except SocketDisconnected, e:
                inMsg = InMsg(InMsg.MSG_HYPERV_DISCONNECTED, \
                              self.client_address)
                self.server.hypervRecvQueue.put((InMsg.PRIO_IMPORTANT, inMsg))
                break

        LOGGER.info("SERVER: Closing %s" % (threading.currentThread()))
        self.stopEvent.clear()
        return
#-------------------------------------------------------------------------------
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
class WebInterface:
    #reference to testMaster
    testMaster = None
    config = None
    #---------------------------------------------------------------------------
    def __init__(self, config, test_master_ref):
        self.testMaster = test_master_ref
        self.config = config
    '''
    Provides web interface for the manager.
    '''
    def index(self):
        tplFile = self.config.get('webserver', 'webpage_dir') \
                    + os.sep + 'main.tmpl'
        LOGGER.info(tplFile)

        tplVars = { 'title' : 'Xrd Test Master - Web Iface',
                    'message' : 'Welcome and begin the tests!',
                    'clusters' : self.testMaster.clustersList,
                    'clustersStats' : self.testMaster.clustersStats,
                    'hypervisors': self.testMaster.hypervisors }

        tpl = Template (file=tplFile, searchList=[tplVars])
        return tpl.respond()
    #---------------------------------------------------------------------------
    def startCluster(self, clusterName):
        LOGGER.info("startCluster pressed: " + str(clusterName))
        self.testMaster.handleClusterStart(clusterName)
        return self.index()

    index.exposed = True
    startCluster.exposed = True
#-------------------------------------------------------------------------------
class XrdTestMaster(Runnable):
    '''
    Runnable class, doing XrdTestMaster jobs.
    '''
    # The list of connected hypervisors
    # e.g. list: { client_address : 
    #              (socket_obj, bin_flag conn_status), }
    hypervisors = {}
    # Locking queue with messages from hypervisors
    hypervRecvQueue = PriorityBlockingQueue()
    # Cluster definitions loaded from a file
    clustersList = []
    # Cluster statuses
    clustersStats = {}
    #global configuration for master
    config = None
    #---------------------------------------------------------------------------
    def __init__(self, config):
        self.config = config
    #---------------------------------------------------------------------------
    def handleClusterStart(self, clusterName):
        clusterFound = False
        for clu in self.clustersList:
            if clu.name == clusterName:
                clusterFound = True
                #choose one Hipervisor arbitrarily
                if len(self.hypervisors):
                    msg = XrdMessage(XrdMessage.MSG_START_CLUSTER)
                    msg.clusterDef = clu

                    addr = None
                    for (k, v) in self.hypervisors.iteritems():
                        addr = k
                        break
                    self.sendMsg(addr, msg)
                else:
                    LOGGER.error("No hipervisor to run the cluster on")
        if not clusterFound:
            LOGGER.error("No cluster with name " + str(clusterName) + " found")
    #---------------------------------------------------------------------------
    def handleHipervDisconnected(self, client_addr):
        #self.hypervisors
        try:
            if self.hypervisors[client_addr][0]:
                self.hypervisors[client_addr][0].close()
        except socket.error, e:
            LOGGER.exception(e)
            pass
        del self.hypervisors[client_addr]
        LOGGER.info("Disconnected: " + str(client_addr))
        LOGGER.info("Supervisors list: " + str(self.hypervisors))
    #---------------------------------------------------------------------------
    def handleHipervConnected(self, client_addr, sock_obj):
        LOGGER.error("Client addr: " + str(client_addr))
        self.hypervisors[client_addr] = (sock_obj, 1)
        LOGGER.info("Supervisors list: " + str(self.hypervisors))
    #---------------------------------------------------------------------------
    def sendMsg(self, receiverAddr, msg):
        '''
        Send message to one of the hypervisors by addr
        @param receiverAddr: addr of hipervisor (IP, port) tuple
        @param msg: message to be sent
        '''
        if self.hypervisors.has_key(receiverAddr):
            try:
                LOGGER.debug('Sending: ' + str(msg.name) + ' to ' \
                             + str(receiverAddr))
                if self.hypervisors[receiverAddr][0]:
                    self.hypervisors[receiverAddr][0].send(msg)
            except SocketDisconnected, e:
                LOGGER.info("Connection to XrdTestHipervisor closed.")
        return
    #---------------------------------------------------------------------------
    def run(self):
        ''' 
        Main jobs of programme. Has to be implemented.
        '''
        global cherrypy, currentDir, cherrypyConfig

        server = ThreadedTCPServer((self.config.get('server', 'ip'), \
                                    self.config.getint('server', 'port')),
                           ThreadedTCPRequestHandler)
        server.testMaster = self
        server.hypervisors = self.hypervisors
        server.hypervRecvQueue = self.hypervRecvQueue

        ip, port = server.server_address
        LOGGER.info("TCP Hipervisor server running " + str(ip) + " " + \
                    str(port))

        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.start()

        cherrypyCfg = {'/webpage/js': {
                     'tools.staticdir.on': True,
                     'tools.staticdir.dir' : \
                     self.config.get('webserver', 'webpage_dir') \
                     + "/js",
                     },
                  '/webpage/css': {
                     'tools.staticdir.on': True,
                     'tools.staticdir.dir' : \
                     self.config.get('webserver', 'webpage_dir') \
                     + "/css",
                     }
                }

        cherrypy.tree.mount(WebInterface(self, self.config), "/", cherrypyCfg)
        cherrypy.config.update({'server.socket_host': '0.0.0.0',
                            'server.socket_port': 8080,})
        cherrypy.server.start()

        self.clustersList = loadClustersDefs(currentDir + "/clusters")

        while True:
            inMsg = self.hypervRecvQueue.get()
            LOGGER.error(str(inMsg))
            if inMsg.type == InMsg.MSG_DATA:
                addrMsg = inMsg.data
                if addrMsg:
                    msg = addrMsg[1]
                    LOGGER.debug("Received from " + str(addrMsg[0]) \
                                 + " msg: " + msg.name)
            elif inMsg.type == InMsg.MSG_HYPERV_CONNECTED:
                self.handleHipervConnected(inMsg.data[0], inMsg.data[1],)
            elif inMsg.type == InMsg.MSG_HYPERV_DISCONNECTED:
                self.handleHipervDisconnected(inMsg.data)
            else:
                raise XrdTestMasterException("Unknown incoming msg type")
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
    #---------------------------------------------------------------------------
    # read the config file
    #---------------------------------------------------------------------------
    global defaultConfFile
    LOGGER.info("Loading config file: %s" % options.configFile)
    try:
        confFile = ''
        if options.configFile:
            confFile = options.confFile
        if not os.path.exists(confFile):
            confFile = defaultConfFile
        config = readConfig(confFile)
        isConfigFileRead = True
    except (RuntimeError, ValueError, IOError), e:
        LOGGER.exception(e)
        sys.exit(1)

    testMaster = XrdTestMaster(config)
    #---------------------------------------------------------------------------
    # run the daemon
    #---------------------------------------------------------------------------
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
    #---------------------------------------------------------------------------
    # run test master in standard mode. Used for debugging
    #---------------------------------------------------------------------------
    if not options.backgroundMode:
        testMaster.run()
#-------------------------------------------------------------------------------
# Start place
#-------------------------------------------------------------------------------
if __name__ == '__main__':
    main()
