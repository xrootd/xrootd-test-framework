#!/usr/bin/env python
#-------------------------------------------------------------------------------
# Author:  Lukasz Trzaska <ltrzaska@cern.ch>
# Date:    
# File:    XrdTestMaster
# Desc:    Xroot Testing Framework manager. Saves all information into logs and
#          displays most important through web interface.
#-------------------------------------------------------------------------------
# Imports
#-------------------------------------------------------------------------------
from Cheetah.Template import Template
from Daemon import Runnable, Daemon, DaemonException, readConfig
from SocketUtils import FixedSockStream, XrdMessage, PriorityBlockingQueue, \
    SocketDisconnectedError
from ClusterManager import Cluster, loadClustersDefs
from TestUtils import loadTestSuitsDefs, TestSuite
from Utils import Stateful, State
from copy import copy
from optparse import OptionParser
import ConfigParser
import SocketServer
import cherrypy
import logging
import os
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
    sender = None #sender addr, tuple (ip, port)
    #---------------------------------------------------------------------------
    def __init__(self, e_type, e_data, msg_sender_addr=None):
        self.type = e_type
        self.data = e_data
        self.sender = msg_sender_addr
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
        self.clientType = ThreadedTCPRequestHandler.C_SLAVE
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

        LOGGER.info(clientType.capitalize() + " [" + str(clientHostname) + \
                                            ", " + str(self.client_address) + \
                                            "] establishing connection...")

        self.clientType = ThreadedTCPRequestHandler.C_SLAVE
        if clientType == ThreadedTCPRequestHandler.C_HYPERV:
            self.clientType = ThreadedTCPRequestHandler.C_HYPERV

        evt = MasterEvent(MasterEvent.M_CLIENT_CONNECTED, (self.clientType,
                            self.client_address, self.sockStream, \
                            clientHostname))

        self.server.recvQueue.put((MasterEvent.PRIO_IMPORTANT, evt))

        while not self.stopEvent.isSet():
            try:
                msg = self.sockStream.recv()
                evtType = MasterEvent.M_SLAVE_MSG
                if self.clientType == self.C_HYPERV:
                    evtType = MasterEvent.M_HYPERV_MSG

                LOGGER.debug("Server: Received msg from %s enqueuing evt: " + str(evtType))
                msg.sender = self.client_address

                evt = MasterEvent(evtType, msg, self.client_address)
                self.server.recvQueue.put((MasterEvent.PRIO_NORMAL, evt))
            except SocketDisconnectedError, e:
                evt = MasterEvent(MasterEvent.M_CLIENT_DISCONNECTED, \
                                  (self.clientType, self.client_address))
                self.server.recvQueue.put((MasterEvent.PRIO_IMPORTANT, evt))
                break

        LOGGER.info("Server: Closing connection with %s [%s]" % \
                                    (clientHostname, self.client_address))
        self.sockStream.close()
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
    #---------------------------------------------------------------------------
    def index(self):
        '''
        Provides web interface for the manager.
        '''
        tplFile = self.config.get('webserver', 'webpage_dir') \
                    + os.sep + 'main.tmpl'
        LOGGER.debug("Loading WebInterface.index(). Template file: " + tplFile)

        tplVars = { 'title' : 'Xrd Test Master - Web Iface',
                    'message' : 'Welcome and begin the tests!',
                    'clusters' : self.testMaster.clusters,
                    'hypervisors': self.testMaster.hypervisors,
                    'suitSessions' : self.testMaster.testSuitsSessions,
                    'slaves': self.testMaster.slaves,
                    'hostname': socket.gethostname(),
                    'testSuits': self.testMaster.testSuits,
                    'userMsg' : self.testMaster.userMsg,
                    'testMaster': self.testMaster,
                    'HTTPport' : '8080'}
        tpl = Template(file=tplFile, searchList=[tplVars])
        return tpl.respond()
    #---------------------------------------------------------------------------
    def indexRedirect(self):
        tplFile = self.config.get('webserver', 'webpage_dir') \
                    + os.sep + 'index_redirect.tmpl'
        tplVars = { 'hostname': socket.gethostname(),
                    'HTTPport' : '8080' }
        tpl = Template(file=tplFile, searchList=[tplVars])
        return tpl.respond()
    #---------------------------------------------------------------------------
    def startCluster(self, clusterName):
        LOGGER.info("startCluster pressed: " + str(clusterName))
        self.testMaster.handleClusterStart(clusterName)
        return self.indexRedirect()
    #---------------------------------------------------------------------------
    def runTest(self, testSuiteName, testName):
        LOGGER.info("Run test pressed - test case [%s] in test suite [%s] " % \
                                (testName, testSuiteName))
        self.testMaster.runTest(testSuiteName, testName)
        return self.indexRedirect()
    #---------------------------------------------------------------------------
    def initSuite(self, testSuiteName):
        LOGGER.info("Init suite pressed - test suite [%s] " % \
                                (testSuiteName))
        self.testMaster.initializeTestSuite(testSuiteName)
        return self.indexRedirect()

    index.exposed = True
    startCluster.exposed = True
    runTest.exposed = True
    initSuite.exposed = True
#-------------------------------------------------------------------------------
class TCPClient(Stateful):
    S_CONNECTED_IDLE    = (1, "Connected")
    S_NOT_CONNECTED     = (2, "Not connected")
    '''
    Represents any type of TCP client that connects to XrdTestMaster.
    '''
    socket = None
    hostname = ""
    address = (None, None)
    #---------------------------------------------------------------------------
    # states of a client
    #---------------------------------------------------------------------------
    def __init__(self, socket, hostname, address, state):
        self.socket = socket
        self.hostname = hostname
        self.state = state
        self.address = address
    #---------------------------------------------------------------------------
    def send(self, msg):
        try:
            LOGGER.debug('Sending: %s to %s[%s]' % (msg.name, self.hostname, \
                                                    str(self.address)))
            self.socket.send(msg)
        except SocketDisconnectedError, e:
            LOGGER.error("Socket to client %s[%s] closed during send." % \
                         (self.hostname, str(self.address)))
#-------------------------------------------------------------------------------
class Hypervisor(TCPClient):
     #--------------------------------------------------------------------------
    def __str__(self):
        return "Hypervisor %s [%s]" % (self.hostname, self.address)
#-------------------------------------------------------------------------------
class Slave(TCPClient):
    #---------------------------------------------------------------------------
    S_SUITINIT_SENT = (10, "Sent test suite init to slave")
    S_SUIT_INITIALIZED = (11, "Test suite init to slave")

    S_TESTCASE_DEF_SENT = (21, "Sent test case definition to slave")
    #---------------------------------------------------------------------------
    def __str__(self):
        return "Slave %s [%s]" % (self.hostname, self.address)
#-------------------------------------------------------------------------------
class TestSuiteSession(Stateful):
    #---------------------------------------------------------------------------
    testSuiteName = ""
    testCases = []
    #---------------------------------------------------------------------------
    # references to slaves who are necessary for the test suite
    slaves = []
    #--------------------------------------------------------------------------
    # keeps the results of some stage. Values tuple (State, Result)
    stagesResults = []
    #---------------------------------------------------------------------------
    def __init__(self, suite_name):
        self.testSuiteName = suite_name
        self.stagesResults = []
        self.slaves = []
    #---------------------------------------------------------------------------
    def addStageResult(self, state, result):
        self.stagesResults.append(state, result)
#-------------------------------------------------------------------------------
class XrdTestMaster(Runnable):
    '''
    Runnable class, doing XrdTestMaster jobs.
    '''
    #---------------------------------------------------------------------------
    # Global configuration for master
    config = None
    #---------------------------------------------------------------------------
    # Priority queue (locking) with incoming events, i.a. incoming messages
    recvQueue = PriorityBlockingQueue()
    #---------------------------------------------------------------------------
    # Connected hypervisors, keys: address tuple, values: TCPClients
    hypervisors = {}
    #---------------------------------------------------------------------------
    # Connected hypervisors, keys: address tuple, values: TCPClients
    slaves = {}
    #---------------------------------------------------------------------------
    # Initialized and in progress test suits
    testSuitsSessions = {}
    #---------------------------------------------------------------------------
    # Definitions of clusters loaded from a file, name as a key
    clusters = {}
    #---------------------------------------------------------------------------
    # Definitions of test suits loaded from file
    testSuits = {}
    #---------------------------------------------------------------------------
    # Constants
    C_SLAVE = 'slave'
    C_HYPERV = 'hypervisor'
    #---------------------------------------------------------------------------
    # messaging system
    userMsg = []
    #---------------------------------------------------------------------------
    def __init__(self, config):
        self.config = config
    #---------------------------------------------------------------------------
    def handleClusterStart(self, clusterName):
        clusterFound = False
        if self.clusters.has_key(clusterName):
            if self.clusters[clusterName].name == clusterName:
                clusterFound = True
                #@todo: choosing hypervisor in more intelligent
                #choose one Hipervisor arbitrarily
                if len(self.hypervisors):
                    msg = XrdMessage(XrdMessage.M_START_CLUSTER)
                    msg.clusterDef = self.clusters[clusterName]
                    
                    #take first possible hypervisor
                    hyperv = [h for h in self.hypervisors.itervalues()][0]
                    hyperv.send(msg)

                    self.clusters[clusterName].state = \
                        State(Cluster.S_UNKNOWN)

                    LOGGER.info("Cluster start command sent to %s", hyperv)
                else:
                    LOGGER.error("No hypervisor to run the cluster on")
                    self.clusters[clusterName].state = \
                    State(Cluster.S_UNKNOWN_NOHYPERV)
        if not clusterFound:
            LOGGER.error("No cluster with name " + str(clusterName) + " found")
    #---------------------------------------------------------------------------
    def initializeTestSuite(self, test_suite_name):
        '''
        Sends initialize message to slaves and creates TestSuite Session.
        @param test_suite_name:
        '''
        testSuite = self.testSuits[test_suite_name]

        # Checks if we already initialized
        if self.testSuitsSessions.has_key(test_suite_name):
            return

        unreadyMachines = []
        for m in testSuite.machines:
            if self.slaveState(m) != State(Slave.S_CONNECTED_IDLE):
                unreadyMachines.append(m)
                LOGGER.error(m + " state " + str(self.slaveState(m)))

        if len(unreadyMachines):
            LOGGER.error("Some required machines are not " + \
                         "ready for the test: %s" % str(unreadyMachines))
            return

        testSlaves = [v for v in self.slaves.itervalues() \
                  if v.hostname in testSuite.machines]

        session = TestSuiteSession(testSuite.name)
        session.slaves = testSlaves
        session.state = State(TestSuite.S_WAIT_4_INIT)

        msg = XrdMessage(XrdMessage.M_TESTSUITE_INIT)
        msg.testSuiteName = testSuite.name
        msg.cmd = testSuite.initialize

        for sl in testSlaves:
            LOGGER.info("Sending Test Suite initialize to %s" % sl)
            sl.send(msg)
            sl.state = State(Slave.S_SUITINIT_SENT)
    #---------------------------------------------------------------------------
    def finalizeTestSuite(self, test_suite_name):
        suite = self.testSuitsSessions[test_suite_name]
        if suite.state == State(TestSuiteSession.S_FINALIZED):
            LOGGER.info("TestSuite already finalized")
        else:
            pass
            #@todo: finalization job
    #---------------------------------------------------------------------------
    def runTest(self, testSuiteName, testName):
        unreadyMachines = []

        if self.testsRunning.has_key(testName):
            LOGGER.error("Test jest w trakcie wykonania.")
            return False

        testSuite = self.testSuits[testSuiteName]
        testCase = testSuite.testCases[testName]

        for m in testCase.machines:
            if self.slaveState(m).id != State(Slave.S_SUIT_INITIALIZED):
                unreadyMachines.append(m)
                LOGGER.error(m + " state " + str(self.slaveState(m)))

        if len(unreadyMachines):
            LOGGER.error("Some required machines are not " + \
                         "ready for the test: %s" % str(unreadyMachines))
        else:
            LOGGER.debug("Before sending test case defs to slaves")
            msg = XrdMessage(XrdMessage.M_TESTCASE_RUN)
            msg.testDef = testCase

            testSlaves = [v for v \
                          in self.slaves.itervalues() \
                          if v.hostname in testCase.machines]

            for sl in testSlaves:
                LOGGER.info("Sending test case def to %s" % (sl))
                sl.sendMsg(msg)

                sl.state = State(Slave.TESTCASE_DEF_SENT)

                LOGGER.debug("TestSuite def sent to slave [%s] " % str(sl))
        return True
    #---------------------------------------------------------------------------
    def handleClientDisconnected(self, client_type, client_addr):
        clients = self.slaves
        if client_type == self.C_HYPERV:
            clients = self.hypervisors

        try:
            if clients[client_addr].socket:
                clients[client_addr].socket.close()
        except socket.error, e:
            LOGGER.exception(e)

        del clients[client_addr]
        LOGGER.info("Disconnected " + str(client_type) + ":" + str(client_addr))
    #---------------------------------------------------------------------------
    def handleClientConnected(self, client_type, client_addr, \
                              sock_obj, client_hostname):
        clients = self.slaves
        if client_type == self.C_HYPERV:
            clients = self.hypervisors

        cliExists = [1 for cname in clients.iterkeys()
                                    if cname == client_hostname]
        if len(cliExists):
            raise XrdTestMasterException(client_type + \
                                         " [" + client_hostname + \
                                         "] already exists. It's name " + \
                                         " has to be unique.")
            #@todo: disconnect client and end its thread
        else:
            if client_type == self.C_SLAVE:
                clients[client_addr] = Slave(sock_obj, client_hostname,
                                             client_addr,
                                             State(TCPClient.S_CONNECTED_IDLE))
            else:
                clients[client_addr] = Hypervisor(sock_obj, client_hostname,
                                            client_addr,
                                            State(TCPClient.S_CONNECTED_IDLE))

            clients_str = [str(c) for c in clients.itervalues()]
            LOGGER.info(str(client_type) + \
                        "s list (after handling incoming connection): " + \
                         ', '.join(clients_str))
    #---------------------------------------------------------------------------
    def slaveState(self, slave_name):
        key = [k for k, v in self.slaves.iteritems() \
               if slave_name == v.hostname]
        ret = State(TCPClient.S_NOT_CONNECTED)
        if len(key):
            key = key[0]
        if key:
            ret = self.slaves[key].state
        return ret
    #---------------------------------------------------------------------------
    def run(self):
        ''' 
        Main jobs of programme. Has to be implemented.
        '''
        global cherrypy, currentDir, cherrypyConfig

        server = None
        try:
            server = ThreadedTCPServer((self.config.get('server', 'ip'), \
                                        self.config.getint('server', 'port')),
                               ThreadedTCPRequestHandler)
        except socket.error, e:
            if e[0] == 98:
                LOGGER.info("Can't start. Socket already in use.")
            else:
                LOGGER.exception(e)
            sys.exit(1)

        server.testMaster = self
        server.config = self.config
        server.recvQueue = self.recvQueue

        ip, port = server.server_address
        LOGGER.info("TCP server running at " + str(ip) + ":" + \
                    str(port))

        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.start()

        clusters = loadClustersDefs(currentDir + "/clusters")
        for clu in clusters:
            myIp = socket.gethostbyname(socket.gethostname())
            self.clusters[clu.name] = clu
            self.clusters[clu.name].state = State(Cluster.S_UNKNOWN)
            self.clusters[clu.name].network.xrdTestMasterIP = myIp
            LOGGER.debug("Master's IP set to %s" % myIp)

        self.testSuits = loadTestSuitsDefs(currentDir + "/testSuits")

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

        while True:
            evt = self.recvQueue.get()
            if evt.type == MasterEvent.M_UNKNOWN:
                msg = evt.data
                LOGGER.debug("Received from " + str(msg.sender) \
                             + " msg: " + msg.name)
            #------------------------------------------------------------------- 
            elif evt.type == MasterEvent.M_CLIENT_CONNECTED:
                self.handleClientConnected(evt.data[0], evt.data[1], \
                                           evt.data[2], evt.data[3])
            #-------------------------------------------------------------------
            elif evt.type == MasterEvent.M_CLIENT_DISCONNECTED:
                self.handleClientDisconnected(evt.data[0], evt.data[1])
            #-------------------------------------------------------------------
            # Messages from hypervisors
            elif evt.type == MasterEvent.M_HYPERV_MSG:
                msg = evt.data
                if msg.name == XrdMessage.M_CLUSTER_STATE:
                    if self.clusters.has_key(msg.clusterName):
                        self.clusters[msg.clusterName].state = msg.state
                        LOGGER.info("Cluster state received [" + \
                                                     msg.clusterName + "] " + \
                                                     str(msg.state))
                    else:
                        raise XrdTestMasterException("Unknown cluster " + \
                                                     "state recvd: " + \
                                                     msg.clusterName)
            #-------------------------------------------------------------------
            # Messages from slaves
            elif evt.type == MasterEvent.M_SLAVE_MSG:
                msg = evt.data
                if msg.name == XrdMessage.M_TESTCASE_STAGE_RESULT:
                    LOGGER.error(msg.name)
                    if self.testsRunning.has_key(msg.testCase):
                        LOGGER.info("STAGE RESULT at " + \
                                    self.slaves[evt.sender].hostname + \
                                    " " + str(msg.result))
                        self.testCaseRunning[msg.testCase][msg.testStage] = \
                                                        msg.result

                        if msg.testStage == "suiteFinalize":
                            del self.testsRunning[msg.testCase]
                    else:
                        raise XrdTestMasterException(("Unknown test case " + \
                                                     " [%s]") % msg.testCase)
                elif msg.name == XrdMessage.M_TESTSUITE_STATE:
                    if msg.state == State(TestSuite.S_SLAVE_INITIALIZED):
                        slave = self.slaves[msg.sender]
                        if slave.state != State(Slave.S_SUITINIT_SENT):
                            XrdTestMasterException("Initialized msg not " + \
                                                   "expected from %s" % slave)
                        else:
                            slave.state = Slave.S_SUIT_INITIALIZED
                            session = self.testSuitsSessions[msg.testSuiteName]
                            session.addStageResult(msg.state, msg.result)
                            #update SauiteStatus if necessary all are inited  
                            initedCount = [1 for sl in session.slaves if sl.status == \
                                        State(Slave.S_SUIT_INITIALIZED)]
                            LOGGER.info("%s initialized in %s" % 
                                            (slave, session.testSuiteName))
                            if len(initedCount) == len(session.slaves):
                                session.status = State(\
                                                TestSuite.S_ALL_INITIALIZED)
                                LOGGER.info("All slaves initialized in %s" % 
                                            session.testSuiteName)
                    elif msg.state == State(TestSuite.S_SLAVE_FINALIZED):
                        self.slaves[msg.sender].state = msg.state
            else:
                raise XrdTestMasterException("Unknown incoming evt type " + \
                                             str(evt.type))
#-------------------------------------------------------------------------------
class UserInfoHandler(logging.Handler):
    testMaster = None
    def __init__(self, xrdTestMaster):
            logging.Handler.__init__(self)
            self.testMaster = xrdTestMaster
    def emit(self, record):
        self.testMaster.userMsg.append(record)
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
    uih = UserInfoHandler(testMaster)
    LOGGER.addHandler(uih)
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
