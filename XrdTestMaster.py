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
from ClusterManager import ClusterManagerException, loadClustersDefs, Status
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
from TestUtils import loadTestSuitsDefs, loadTestCasesDefs
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
class MasterEvent(object):
    '''
    The message incoming to XrdTestMaster. May be either the event e.g.
    hypervisor connection or normal message containing data.
    '''
    PRIO_NORMAL = 9
    PRIO_IMPORTANT = 1

    M_UNKNOWN = 1
    M_CLIENT_CONNECTED = 2
    M_CLIENT_DISCONNECTED = 4
    M_HYPERV_MSG = 8
    M_SLAVE_MSG = 16

    type = M_UNKNOWN
    data = ''
    sender = None
    #---------------------------------------------------------------------------
    def __init__(self, e_type, e_data, msg_sender = None):
        self.type = e_type
        self.data = e_data
        self.sender = msg_sender

#-------------------------------------------------------------------------------
class ThreadedTCPRequestHandler(SocketServer.BaseRequestHandler):
    """
    Client's request handler.
    """
    C_SLAVE = "slave"
    C_HYPERV = "hypervisor"
    clientType = ""
    #---------------------------------------------------------------------------
    def setup(self):
        '''
        Initiate class properties
        '''
        self.stopEvent = threading.Event()
        self.stopEvent.clear()
        self.sockStream = None
        self.clientType=ThreadedTCPRequestHandler.C_SLAVE
    #---------------------------------------------------------------------------
    def authClient(self):
        '''
        Check if hypervisor is authentic
        '''
        msg = self.sockStream.recv()
        if msg == self.server.config.get('server', 'connection_passwd'):
            self.sockStream.send('PASSWD_OK')
        else:
            self.sockStream.send('PASSWD_WRONG')
            LOGGER.info("Incoming hypervisor connection rejected. " + \
                        "It didn't provide correct password")
            return
        return True
    #---------------------------------------------------------------------------
    def handle(self):
        '''
        Handle new incoming connection and keep it to receive messages.
        '''
        global LOGGER

        self.sockStream = ssl.wrap_socket(self.request, server_side=True,
                                          certfile=\
                                self.server.config.get('security', 'certfile'),
                                          keyfile=\
                                self.server.config.get('security', 'keyfile'),
                                          ssl_version=ssl.PROTOCOL_TLSv1)
        self.sockStream = FixedSockStream(self.sockStream)

        self.authClient()
        (clientType, clientHostname) = self.sockStream.recv()

        LOGGER.info(clientType + " starting connection...")

        self.clientType = ThreadedTCPRequestHandler.C_SLAVE
        if clientType == ThreadedTCPRequestHandler.C_HYPERV:
            self.clientType = ThreadedTCPRequestHandler.C_HYPERV

        evt = MasterEvent(MasterEvent.M_CLIENT_CONNECTED, (self.clientType,
                            self.client_address, self.sockStream,\
                            clientHostname))

        self.server.recvQueue.put((MasterEvent.PRIO_IMPORTANT, evt))

        while not self.stopEvent.isSet():
            try:
                msg = self.sockStream.recv()
                evtType = MasterEvent.M_SLAVE_MSG
                if self.clientType == self.C_HYPERV:
                    evtType = MasterEvent.M_HYPERV_MSG

                LOGGER.info("Received message, enqueuing evt: " + str(evtType))
                evt = MasterEvent(evtType, msg, self.client_address)
                self.server.recvQueue.put((MasterEvent.PRIO_NORMAL, evt))
            except SocketDisconnected, e:
                evt = MasterEvent(MasterEvent.M_CLIENT_DISCONNECTED,\
                                  (self.clientType, self.client_address))
                self.server.recvQueue.put((MasterEvent.PRIO_IMPORTANT, evt))
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
                    'clusters' : self.testMaster.clusters,
                    'hypervisors': self.testMaster.hypervisors,
                    'slaves': self.testMaster.slaves,
                    'hostname': socket.gethostname(), 
                    'HTTPport' : '8080'}

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
    # The list of connected slaves
    # e.g. list: { client_address : 
    #              (socket_obj, bin_flag conn_status), }
    slaves = {}
    # Locking queue with messages from hypervisors
    recvQueue = PriorityBlockingQueue()
    # Cluster definitions loaded from a file, name as a key
    clusters = {}
    #global configuration for master
    config = None

    C_SLAVE = 'slave'
    C_HYPERV = 'hypervisor'

    #---------------------------------------------------------------------------
    def __init__(self, config):
        self.config = config
    #---------------------------------------------------------------------------
    def handleClusterStart(self, clusterName):
        clusterFound = False
        if self.clusters.has_key(clusterName):
            if self.clusters[clusterName].name == clusterName:
                clusterFound = True
                #choose one Hipervisor arbitrarily
                if len(self.hypervisors):
                    msg = XrdMessage(XrdMessage.M_START_CLUSTER)
                    msg.clusterDef = self.clusters[clusterName]

                    addr = None
                    for (k, v) in self.hypervisors.iteritems():
                        addr = k
                        break
                    self.sendMsg(addr, msg)
                    self.clusters[clusterName].status = \
                        Status("Cluster def sent to hypervisor: " + \
                               str(addr))
                    LOGGER.debug("Cluster def sent to hypervisor " + \
                                 str(addr))
                else:
                    LOGGER.error("No hypervisor to run the cluster on")
                    self.clusters[clusterName].status = \
                    Status(Status.S_IDLE_NO_PLACE)
        if not clusterFound:
            LOGGER.error("No cluster with name " + str(clusterName) + " found")
    #---------------------------------------------------------------------------
    def handleClientDisconnected(self, client_type, client_addr):
        clients = self.slaves
        if client_type == self.C_HYPERV:
            clients = self.hypervisors

        try:
            if clients[client_addr][0]:
                clients[client_addr][0].close()
        except socket.error, e:
            LOGGER.exception(e)

        del clients[client_addr]
        LOGGER.info("Disconnected " + str(client_type) + ":" + str(client_addr))
    #---------------------------------------------------------------------------
    def handleClientConnected(self, client_type, client_addr, sock_obj,\
                               client_hostname):
        clients = self.slaves
        if client_type == self.C_HYPERV:
            clients = self.hypervisors

        LOGGER.info("Client addr: " + str(client_addr))
        clients[client_addr] = (sock_obj, client_hostname)
        LOGGER.info(str(client_type) + "s: " + str(clients))
    #---------------------------------------------------------------------------
    def sendMsg(self, receiver_addr, msg):
        '''
        Send message to one of the hypervisors by addr
        @param receiverAddr: addr of hipervisor (IP, port) tuple
        @param msg: message to be sent
        '''
        if self.hypervisors.has_key(receiver_addr):
            try:
                LOGGER.debug('Sending: ' + str(msg.name) + ' to ' \
                             + str(receiver_addr))
                if self.hypervisors[receiver_addr][0]:
                    self.hypervisors[receiver_addr][0].send(msg)
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
        server.config = self.config
        server.recvQueue = self.recvQueue

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

        cherrypy.tree.mount(WebInterface(self.config, self), "/", cherrypyCfg)
        cherrypy.config.update({'server.socket_host': '0.0.0.0',
                            'server.socket_port': 8080, })
        cherrypy.server.start()

        clusters = loadClustersDefs(currentDir + "/clusters")
        for clu in clusters:
            self.clusters[clu.name] = clu
            clu.status = Status(Status.S_IDLE)
            if len(clu.hosts):
                for h in clu.hosts:
                    h.status = Status(Status.S_IDLE)

        testSuits = loadTestSuitsDefs(currentDir + "/testSuits")

        testCases = loadTestCasesDefs(currentDir + "/testCases")

        while True:
            evt = self.recvQueue.get()
            if evt.type == MasterEvent.M_UNKNOWN:
                msg = evt.data
                LOGGER.debug("Received from " + str(msg.sender) \
                             + " msg: " + msg.name)
            elif evt.type == MasterEvent.M_CLIENT_CONNECTED:
                self.handleClientConnected(evt.data[0], evt.data[1], \
                                           evt.data[2], evt.data[3])
            elif evt.type == MasterEvent.M_CLIENT_DISCONNECTED:
                self.handleClientDisconnected(evt.data[0], evt.data[1])
            elif evt.type == MasterEvent.M_HYPERV_MSG:
                msg = evt.data
                if msg.name == XrdMessage.M_CLUSTER_STATUS:
                    LOGGER.error(msg.name)
                    if self.clusters.has_key(msg.clusterName):
                        self.clusters[msg.clusterName].status = \
                        Status(msg.status)
                        LOGGER.info("Cluster status received [" + \
                                                     msg.clusterName + "] " + \
                                                     str(msg.status))
                    else:
                        raise XrdTestMasterException("Unknown cluster " + \
                                                     "status recvd: " + \
                                                     msg.clusterName)
            else:
                raise XrdTestMasterException("Unknown incoming evt type " + \
                                             str(evt.type))
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
