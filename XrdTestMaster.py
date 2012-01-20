#!/usr/bin/env python
#-------------------------------------------------------------------------------
# Author:  Lukasz Trzaska <ltrzaska@cern.ch>
# Date:    
# File:    XrdTestMaster
# Desc:    Xroot Testing Framework manager. Saves all information into logs and
#          displays most important through web interface.
#-------------------------------------------------------------------------------
# Logging settings
#-------------------------------------------------------------------------------
from cherrypy import _cperror
from multiprocessing import process
import Cheetah
import logging
import sys
from curses.has_key import has_key
import datetime
logging.basicConfig(format='%(asctime)s %(levelname)s ' + \
                    '[%(filename)s %(lineno)d] ' + \
                    '%(message)s', level=logging.INFO)
LOGGER = logging.getLogger(__name__)
LOGGER.debug("Running script: " + __file__)
#-------------------------------------------------------------------------------
# Imports
#-------------------------------------------------------------------------------
try:
    from Cheetah.Template import Template
    from ClusterManager import Cluster, loadClustersDefs
    from Daemon import Runnable, Daemon, DaemonException, readConfig
    from SocketUtils import FixedSockStream, XrdMessage, PriorityBlockingQueue, \
        SocketDisconnectedError
    from TestUtils import loadTestSuitsDefs, TestSuite
    from Utils import Stateful, State
    from copy import copy
    from optparse import OptionParser
    import ConfigParser
    import SocketServer
    import cherrypy
    import os
    import signal
    import socket
    import ssl
    import threading
    import time
except ImportError, e:
    LOGGER.error(str(e))
    sys.exit(1)
#-------------------------------------------------------------------------------
# Globals and configurations
#-------------------------------------------------------------------------------
currentDir = os.path.dirname(os.path.abspath(__file__))
#Default daemon configuration
defaultConfFile = './XrdTestMaster.conf'
defaultPidFile = '/var/run/XrdTestMaster.pid'
defaultLogFile = '/var/log/XrdTest/XrdTestMaster.log'

tcpServer = None
xrdTestMaster = None
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

    M_SIGTERM = 128

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
class XrdTCPServer(SocketServer.TCPServer):
    allow_reuse_address = True
#-------------------------------------------------------------------------------
class ThreadedTCPServer(SocketServer.ThreadingMixIn, XrdTCPServer):
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
#------------------------------------------------------------------------------ 
def handleCherrypyError():
        cherrypy.response.status = 500
        cherrypy.response.body = \
                        ["An error occured. Check log for details."]
        LOGGER.error("Cherrypy error: " + \
                     str(_cperror.format_exc(None))) #@UndefinedVariable
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
                    'userMsgs' : self.testMaster.userMsgs,
                    'testMaster': self.testMaster,
                    'HTTPport' : self.config.getint('webserver', 'port')}
        tpl = None
        try:
            tpl = Template(file=tplFile, searchList=[tplVars])
        except Exception, e:
            LOGGER.error(str(e))
            return "An error occured. Check log for details."
        else:
            return tpl.respond()
    #---------------------------------------------------------------------------
    def indexRedirect(self):
        tplFile = self.config.get('webserver', 'webpage_dir') \
                    + os.sep + 'index_redirect.tmpl'
        tplVars = { 'hostname': socket.gethostname(),
                    'HTTPport': self.config.getint('webserver', 'port')}
        tpl = None
        try:
            tpl = Template(file=tplFile, searchList=[tplVars])
        except Exception, e:
            LOGGER.error(str(e))
            return "Error occured. Check the log for details."
        else:
            return tpl.respond()
    #---------------------------------------------------------------------------
    def startCluster(self, clusterName):
        LOGGER.info("startCluster pressed: " + str(clusterName))
        self.testMaster.handleClusterStart(clusterName)
        return self.indexRedirect()
    #---------------------------------------------------------------------------
    def initSuite(self, testSuiteName):
        LOGGER.info("Initialize requested for test suite [%s] " % \
                                (testSuiteName))
        self.testMaster.initializeTestSuite(testSuiteName)
        return self.indexRedirect()
        #---------------------------------------------------------------------------
    def finalizeSuite(self, testSuiteName):
        LOGGER.info("Finalize requested for test suite [%s] " % \
                                (testSuiteName))
        self.testMaster.finalizeTestSuite(testSuiteName)
        return self.indexRedirect()
    #---------------------------------------------------------------------------
    def runTestCase(self, testSuiteName, testName):
        LOGGER.info("RunTestCase requested for test %s in test suite: %s" % \
                                (testName, testSuiteName))
        self.testMaster.runTestCase(testSuiteName, testName)
        return self.indexRedirect()

    index.exposed = True
    startCluster.exposed = True
    runTestCase.exposed = True
    initSuite.exposed = True
    finalizeSuite.exposed = True

    _cp_config = {'request.error_response': handleCherrypyError}
#-------------------------------------------------------------------------------
class TCPClient(Stateful):
    S_CONNECTED_IDLE = (1, "Connected")
    S_NOT_CONNECTED = (2, "Not connected")
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
            LOGGER.debug('Sending: %s to %s[%s]' % \
                        (msg.name, self.hostname, str(self.address)))
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
    S_SUITINIT_SENT     = (10, "Test suite init sent to slave")
    S_SUIT_INITIALIZED  = (11, "Test suite initialized")

    S_TESTCASE_DEF_SENT = (21, "Sent test case definition to slave")
    #---------------------------------------------------------------------------
    def __str__(self):
        return "Slave %s [%s]" % (self.hostname, self.address)
#-------------------------------------------------------------------------------
class TestSuiteSession(Stateful):
    #---------------------------------------------------------------------------
    suiteName = ""
    #---------------------------------------------------------------------------
    # test cases loaded to run in this session
    cases = {}
    #---------------------------------------------------------------------------
    # references to slaves who are necessary for the test suite
    slaves = []
    #--------------------------------------------------------------------------
    # keeps the results of some stage. Values tuple (State, Result)
    stagesResults = []
    # unique identifier
    uid = ""
    #---------------------------------------------------------------------------
    def __init__(self, suite_name):
        self.suiteName = suite_name
        d = datetime.datetime.now()
        self.uid = suite_name + "_" + d.isoformat()
    #---------------------------------------------------------------------------
    def addCase(self, tc):
        '''
        @param tc: TestCase object
        '''
        d = datetime.datetime.now()
        tc.uid = tc.name + "_" + d.isoformat()
        if not self.cases.has_key(tc):
            self.cases[tc.name] = []
        self.cases[tc.name].append(tc)
        return len(self.cases[tc.name])-1
    #---------------------------------------------------------------------------
    def getCase(self, tcName, idx):
        '''
        @param tc: TestCase object
        '''
        return self.cases[tcName][idx]
        #---------------------------------------------------------------------------
    def getAllCases(self):
        '''
        @param tc: TestCase object
        '''
        res = []
        for v in self.cases.itervalues():
            res += v
            
        return res
    #---------------------------------------------------------------------------
    def addStageResult(self, state, result):
        LOGGER.info("New stage result %s: (code %s) %s" % \
                    (state, result[2], result[0]))
        self.stagesResults.append((state, result))
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
    # Connected hypervisors, keys: address tuple, values: Hypervisor
    hypervisors = {}
    #---------------------------------------------------------------------------
    # Connected slaves, keys: address tuple, values: Slaves
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
    # message logging system
    userMsgs = []
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

                    #take first possible hypervisor and send him cluster def
                    hyperv = [h for h in self.hypervisors.itervalues()][0]
                    hyperv.send(msg)

                    self.clusters[clusterName].state = \
                        State(Cluster.S_UNKNOWN)

                    LOGGER.info("Cluster start command sent to %s", hyperv)
                else:
                    LOGGER.warning("No hypervisor to run the cluster on")
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
                LOGGER.warning(m + " state " + str(self.slaveState(m)))

        if len(unreadyMachines):
            LOGGER.warning("Some required machines are not " + \
                         "ready for the test: %s" % str(unreadyMachines))
            return

        testSlaves = [v for v in self.slaves.itervalues() \
                  if v.hostname in testSuite.machines]

        session = TestSuiteSession(testSuite.name)
        session.slaves = testSlaves
        session.state = State(TestSuite.S_WAIT_4_INIT)

        self.testSuitsSessions[test_suite_name] = session

        msg = XrdMessage(XrdMessage.M_TESTSUITE_INIT)
        msg.suiteName = testSuite.name
        msg.cmd = testSuite.initialize

        for sl in testSlaves:
            LOGGER.info("Sending Test Suite initialize to %s" % sl)
            sl.send(msg)
            sl.state = State(Slave.S_SUITINIT_SENT)
    #---------------------------------------------------------------------------
    def runTestCase(self, test_suite_name, test_name):
        '''
        Sends runTest message to slaves.
        @param test_suite_name:
        @param test_name:
        '''
        # Checks if we already initialized suite
        if not self.testSuitsSessions.has_key(test_suite_name):
            LOGGER.warning("Test Suite %s has not been initialized." % \
                            test_suite_name)
            return

        tss = self.testSuitsSessions[test_suite_name]
        if not tss.state == State(TestSuite.S_ALL_INITIALIZED):
            LOGGER.warning("TestSuite %s has not been initialized." % \
                            test_suite_name)
            return

        # copy test case to test suite session context
        tc = copy(self.testSuits[test_suite_name].testCases[test_name])
        tss.addCase(tc)

        msg = XrdMessage(XrdMessage.M_TESTCASE_RUN)
        msg.suiteName = test_suite_name
        msg.testName = test_name
        msg.testUid = tc.uid
        msg.case = tc

        for sl in tss.slaves:
            LOGGER.info("Sending Test Case %s to %s" % (test_name, sl))
            sl.send(msg)
            sl.state = State(Slave.S_TESTCASE_DEF_SENT)

        tss.state = State(TestSuite.S_TEST_SENT)
    #---------------------------------------------------------------------------
    def finalizeTestSuite(self, test_suite_name):
        '''
        Sends finalization message to slaves and destroys TestSuiteSession.
        @param test_suite_name:
        '''
        testSuite = self.testSuits[test_suite_name]

        # Checks if we already initialized suite
        if not self.testSuitsSessions.has_key(test_suite_name):
            LOGGER.warning("TestSuite has not been initialized.")
            return

        tss = self.testSuitsSessions[test_suite_name]
        if not tss.state == State(TestSuite.S_ALL_INITIALIZED):
            LOGGER.warning("TestSuite not yet initialized.")
            return

        unreadyMachines = []
        for m in testSuite.machines:
            if self.slaveState(m) != State(Slave.S_CONNECTED_IDLE):
                unreadyMachines.append(m)
                LOGGER.warning(m + " state " + str(self.slaveState(m)))

        if len(unreadyMachines):
            LOGGER.warning("Some required machines are not " + \
                         " ready for the finalize: %s" % str(unreadyMachines))
            return

        msg = XrdMessage(XrdMessage.M_TESTSUITE_FINALIZE)
        msg.suiteName = test_suite_name

        for sl in tss.slaves:
            LOGGER.debug("Sending Test Suite finalize to %s" % sl)
            sl.send(msg)
            sl.state = State(Slave.S_SUITFINALIZE_SENT)

        tss.state = State(TestSuite.S_WAIT_4_FINALIZE)

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
            LOGGER.info(str(client_type).title() + \
                        "s list (after handling incoming connection): " + \
                         ', '.join(clients_str))
    #---------------------------------------------------------------------------
    def procMessages(self):
        '''
        Receives events and messages from clients and reacts. Actual place 
        of program control.
        '''
        while True:
            evt = self.recvQueue.get()

            if evt.type == MasterEvent.M_UNKNOWN:
                msg = evt.data
                LOGGER.debug("Received from " + str(msg.sender) \
                             + " msg: " + msg.name)
            elif evt.type == MasterEvent.M_SIGTERM:
                LOGGER.info("Process messages thread received SIGTERM. Ending.")
                break
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
                    if self.testsRunning.has_key(msg.testCase):
                        LOGGER.info("STAGE RESULT at " + \
                                    self.slaves[evt.sender].hostname + \
                                    " " + str(msg.result))
                        self.testCaseRunning[msg.testCase][msg.testStage] = \
                                                        msg.result

                        if msg.testStage == "1":
                            del self.testsRunning[msg.testCase]
                    else:
                        raise XrdTestMasterException(("Unknown test case " + \
                                                     " [%s]") % msg.testCase)
                elif msg.name == XrdMessage.M_TESTSUITE_STATE:
                    if msg.state == State(TestSuite.S_SLAVE_INITIALIZED):
                        slave = self.slaves[msg.sender]
                        if slave.state != State(Slave.S_SUITINIT_SENT):
                            #previous state of slave is not correct, should be
                            #suitinit sent
                            XrdTestMasterException("Initialized msg not " + \
                                                   "expected from %s" % slave)
                        else:
                            slave.state = State(Slave.S_SUIT_INITIALIZED)
                            session = self.testSuitsSessions[msg.suiteName]

                            session.addStageResult(msg.state, msg.result)
                            #update SuiteStatus if all slaves are inited
                            initedCount = [1 for sl in session.slaves if \
                                           sl.state == \
                                           State(Slave.S_SUIT_INITIALIZED)]
                            LOGGER.info("%s initialized in test suite %s" %
                                            (slave, session.suiteName))
                            if len(initedCount) == len(session.slaves):
                                session.state = State(\
                                                TestSuite.S_ALL_INITIALIZED)
                                LOGGER.info("All slaves initialized in " + \
                                            " test suite %s" %
                                            session.suiteName)
                    elif msg.state == State(TestSuite.S_SLAVE_FINALIZED):
                        self.slaves[msg.sender].state = msg.state
                        slave.state = State(Slave.S_CONNECTED_IDLE)
                        finalizedCount = [1 for sl in session.slaves if \
                                           sl.state == \
                                           State(Slave.S_CONNECTED_IDLE)]
                        if len(finalizedCount) == len(session.slaves):
                                session.state = State(\
                                                TestSuite.S_ALL_FINALIZED)
                        LOGGER.info("%s finalized in test suite: %s" % 
                                    (slave, session.suiteName))
                    elif msg.state == State(TestSuite.S_TESTCASE_INITIALIZED):
                        session.addStageResult(msg.state, msg.result)
                        LOGGER.info("%s initialized case %s in suite %s" % 
                                    (slave, msg.testName, session.suiteName))
                    elif msg.state == State(TestSuite.S_TESTCASE_RUNFINISHED):
                        session.addStageResult(msg.state, msg.result)
                        LOGGER.info("%s run finished for case %s in suite %s" % 
                                    (slave, msg.testName, session.suiteName))
                    elif msg.state == State(TestSuite.S_TESTCASE_FINALIZED):
                        session.addStageResult(msg.state, msg.result)
                        slave.state = State(Slave.S_SUIT_INITIALIZED)
                        tFinalizedCount = [1 for sl in session.slaves if \
                                           sl.state == \
                                           State(Slave.S_CONNECTED_IDLE)]
                        if len(tFinalizedCount) == len(session.slaves):
                            session.state = State(TestSuite.S_ALL_INITIALIZED)

                        LOGGER.info("%s finalized test case %s in suite %s" % 
                                (slave, msg.testName, session.suiteName))
            else:
                raise XrdTestMasterException("Unknown incoming evt type " + \
                                             str(evt.type))
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
        Starting jobs of the program.
        '''
        global currentDir, cherrypyConfig
        global cherrypy, tcpServer

        server = None
        try:
            server = ThreadedTCPServer((self.config.get('server', 'ip'), \
                                        self.config.getint('server', 'port')),
                               ThreadedTCPRequestHandler)
        except socket.error, e:
            if e[0] == 98:
                LOGGER.info("Can't start server. Address already in use.")
            else:
                LOGGER.exception(e)
            sys.exit(1)

        tcpServer = server
        server.testMaster = self
        server.config = self.config
        server.recvQueue = self.recvQueue

        ip, port = server.server_address
        LOGGER.info("TCP server running at " + str(ip) + ":" + \
                    str(port))

        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()

        clusters = loadClustersDefs(currentDir + "/clusters")
        for clu in clusters:
            self.clusters[clu.name] = clu
            self.clusters[clu.name].state = State(Cluster.S_UNKNOWN)

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
        #-----------------------------------------------------------------------
        cherrypy.tree.mount(WebInterface(self.config, self), "/", cherrypyCfg)
        cherrypy.config.update({'server.socket_host': '0.0.0.0',
                            'server.socket_port': \
                            self.config.getint('webserver', 'port'),
                            'server.environment': 'production'
                            })
        #-----------------------------------------------------------------------
        try:
            cherrypy.server.start()
        except cherrypy._cperror.Error, e:
            LOGGER.error(str(e))
            if server:
                server.shutdown()
            sys.exit(1)
        #-----------------------------------------------------------------------
        self.procMessages()
#-------------------------------------------------------------------------------
class UserInfoHandler(logging.Handler):
    testMaster = None
    def __init__(self, xrdTestMaster):
            logging.Handler.__init__(self)
            self.testMaster = xrdTestMaster
    def emit(self, record):
        self.testMaster.userMsgs.append(record)

#-------------------------------------------------------------------------------
def sigintHandler(signum, frame):
    #@todo: cannot handle sigint because of python issue signal vs. conditions
    global cherrypy, tcpServer, xrdTestMaster

    LOGGER.error("Received SIGINT. Closing jobs.")
    cherrypy.server.stop()
    evt = MasterEvent(MasterEvent.M_SIGTERM, None)
    xrdTestMaster.recvQueue.put((MasterEvent.PRIO_IMPORTANT, evt))

    tcpServer.shutdown()
    LOGGER.error("Received SIGINT. Closing jobs done.")
    sys.exit(0)

#signal.signal(signal.SIGTERM, sigtermHandler)
signal.signal(signal.SIGINT, sigintHandler)
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
    global xrdTestMaster, defaultConfFile
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

    xrdTestMaster = XrdTestMaster(config)
    uih = UserInfoHandler(xrdTestMaster)
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
                dm.start(xrdTestMaster)
            elif options.backgroundMode == 'stop':
                dm.stop()
            elif options.backgroundMode == 'check':
                res = dm.check()
                LOGGER.info('Result of runnable check: %s' % str(res))
            elif options.backgroundMode == 'reload':
                dm.reload()
                LOGGER.info('You can either start, stop, check or ' + \
                            + 'reload the deamon')
                sys.exit(3)
        except (DaemonException, RuntimeError, ValueError, IOError), e:
            LOGGER.exception('')
            sys.exit(1)
    #---------------------------------------------------------------------------
    # run test master in standard mode. Used for debugging
    #---------------------------------------------------------------------------
    if not options.backgroundMode:
        xrdTestMaster.run()
#-------------------------------------------------------------------------------
# Start place
#-------------------------------------------------------------------------------
if __name__ == '__main__':
    try:
        main()
    except OSError, e:
        LOGGER.error(str(e))
        sys.exit(1)
