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
import logging
import sys

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
    from ClusterManager import ClusterManagerException, extractClusterName, \
    loadClusterDef, loadClustersDefs, Cluster
    from Daemon import Runnable, Daemon, DaemonException, readConfig
    from SocketUtils import FixedSockStream, XrdMessage, PriorityBlockingQueue, \
        SocketDisconnectedError
    from TestUtils import TestSuiteException, loadTestSuiteDef,\
    loadTestSuitsDefs, TestSuite, extractSuiteName
    from apscheduler.scheduler import Scheduler
    from Utils import Stateful, State
    from copy import copy
    from optparse import OptionParser
    import ConfigParser
    import SocketServer
    import cherrypy
    from cherrypy.lib.static import serve_file
    import os
    import socket
    import ssl
    from copy import deepcopy
    from string import maketrans
    import threading
    from pyinotify import WatchManager, Notifier, ThreadedNotifier, ProcessEvent
    import datetime
    import shelve
except ImportError, e:
    LOGGER.error(str(e))
    sys.exit(1)
#-------------------------------------------------------------------------------
# Globals and configurations
#-------------------------------------------------------------------------------
currentDir = os.path.dirname(os.path.abspath(__file__))
os.chdir(currentDir)
#Default daemon configuration
defaultConfFile = '/etc/XrdTest/XrdTestMaster.conf'
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
    M_CLIENT_DISCONNECTED = 3
    M_HYPERV_MSG = 4
    M_SLAVE_MSG = 5
    M_JOB_ENQUEUE = 6
    M_RELOAD_CLUSTER_DEF = 7
    M_RELOAD_SUIT_DEF = 8

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
                     str(cherrypy._cperror.format_exc(None))) #@UndefinedVariable
#-------------------------------------------------------------------------------
class WebInterface:
    #reference to testMaster
    testMaster = None
    config = None
    cp_config = {}

    #---------------------------------------------------------------------------
    def __init__(self, config, test_master_ref):
        self.testMaster = test_master_ref
        self.config = config

        self.cp_config = {'request.error_response': handleCherrypyError,
                          'error_page.404': \
                          self.config.get('webserver', 'webpage_dir') + \
                          os.sep + "page_404.tmpl"}
    #---------------------------------------------------------------------------
    def disp(self, tpl_file, tpl_vars):
        tpl = None
        tplFile = self.config.get('webserver', 'webpage_dir') \
                    + os.sep + tpl_file

        tpl_vars['HTTPport'] = self.config.getint('webserver', 'port')
        try:
            tpl = Template(file=tplFile, searchList=[tpl_vars])
        except Exception, e:
            LOGGER.error(str(e))
            return "An error occured. Check log for details."
        else:
            return tpl.respond()
    #---------------------------------------------------------------------------
    def index(self):
        '''
        Provides web interface for the manager.
        '''
        tplVars = { 'title' : 'Xrd Test Master - Web Iface',
                    'message' : 'Welcome and begin the tests!',
                    'clusters' : self.testMaster.clusters,
                    'hypervisors': self.testMaster.hypervisors,
                    'suitsSessions' : self.testMaster.suitsSessions,
                    'runningSuitsUids' : self.testMaster.runningSuitsUids,
                    'slaves': self.testMaster.slaves,
                    'hostname': socket.gethostname(),
                    'testSuits': self.testMaster.testSuits,
                    'userMsgs' : self.testMaster.userMsgs,
                    'testMaster': self.testMaster, }
        return self.disp("main.tmpl", tplVars)
    #---------------------------------------------------------------------------
    def suitsSessions(self):
        '''
        Provides web interface for the manager.
        '''
        tplVars = { 'title' : 'Xrd Test Master - Web Iface',
                    'suitsSessions' : self.testMaster.suitsSessions,
                    'runningSuitsUids' : self.testMaster.runningSuitsUids,
                    'slaves': self.testMaster.slaves,
                    'hostname': socket.gethostname(),
                    'testSuits': self.testMaster.testSuits,
                    'testMaster': self.testMaster,
                    'HTTPport' : self.config.getint('webserver', 'port')}
        return self.disp("suits_sessions.tmpl", tplVars)
    #---------------------------------------------------------------------------
    def indexRedirect(self):
        tplVars = { 'hostname': socket.gethostname(),
                    'HTTPport': self.config.getint('webserver', 'port')}
        return self.disp("index_redirect.tmpl", tplVars)
    #---------------------------------------------------------------------------
    def startCluster(self, clusterName):
        LOGGER.info("startCluster in mainte pressed: " + str(clusterName))
        self.testMaster.startCluster(clusterName, maintenance=True)
        return self.indexRedirect()
    #---------------------------------------------------------------------------
    def stopCluster(self, clusterName):
        LOGGER.info("stopCluster pressed: " + str(clusterName))
        self.testMaster.stopCluster(clusterName, maintenance=True)
        return self.indexRedirect()
    #--------------------------------------------------------------------------- 
    def downloadScript(self, script_name):
        from xml.sax.saxutils import quoteattr
        p = self.config.get('webserver', 'webpage_dir') \
                + os.sep + 'scripts' + os.sep + quoteattr(script_name)

        if os.path.exists(p):
            return serve_file(p , "application/x-download", "attachment")
        else:
            return ""
    #--------------------------------------------------------------------------- 
    def showScript(self, script_name):
        from xml.sax.saxutils import quoteattr
        p = self.config.get('webserver', 'webpage_dir') \
                          + os.sep + 'scripts' + os.sep + \
                          quoteattr(script_name)
        if os.path.exists(p):
            return serve_file(p , "text/html")
        else:
            return ""

#    startCluster.exposed = True
#    stopCluster.exposed = True
    index.exposed = True
    suitsSessions.exposed = True
    downloadScript.exposed = True
    showScript.exposed = True

#-------------------------------------------------------------------------------
class TCPClient(Stateful):
    S_CONNECTED_IDLE = (1, "Connected")
    S_NOT_CONNECTED = (2, "Not connected")
    '''
    Represents any type of TCP client that connects to XrdTestMaster.
    '''
    #---------------------------------------------------------------------------
    # states of a client
    #---------------------------------------------------------------------------
    def __init__(self, socket, hostname, address, state):
        Stateful.__init__(self)
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
    #---------------------------------------------------------------------------
    def __str__(self):
        return "Hypervisor %s [%s]" % (self.hostname, self.address)
#-------------------------------------------------------------------------------
class Slave(TCPClient):
    #---------------------------------------------------------------------------
    S_SUITINIT_SENT = (10, "Test suite init sent to slave")
    S_SUIT_INITIALIZED = (11, "Test suite initialized")
    S_SUITFINALIZE_SENT = (12, "Test suite finalize sent to slave")

    S_TEST_INIT_SENT = (21, "Sent test case init to slave")
    S_TEST_INITIALIZED = (22, "Test case initialized")
    S_TEST_RUN_SENT = (23, "Sent test case run to slave")
    S_TEST_RUN_FINISHED = (24, "Test case run finished")
    S_TEST_FINALIZE_SENT = (25, "Sent test case finalize to slave")
    #S_TEST_FINALIZED        = Slave.S_SUIT_INITIALIZED
    #---------------------------------------------------------------------------
    def __str__(self):
        return "Slave %s [%s]" % (self.hostname, self.address)
#-------------------------------------------------------------------------------
class TestSuiteSession(Stateful):
    #---------------------------------------------------------------------------
    def __init__(self, suite):
        Stateful.__init__(self)
        # name of test suite
        self.name = suite.name
        # test suite definition copy
        self.suite = deepcopy(suite)
        # date of initialization
        self.initDate = datetime.datetime.now()
        # references to slaves who are necessary for the test suite
        self.slaves = []
        # keeps the results of each stage.
        self.stagesResults = []
        # unique identifier of test suite
        self.uid = self.suite.name + '-' + self.initDate.isoformat()
        self.uid = self.uid.translate(maketrans('', ''), '-:.')# remove special
                                                            # chars from uid
        # test cases loaded to run in this session, key is tc.uid
        self.cases = {}
        # uid of last test case with a name 
        self.caseUidByName = {}

        #if result of any stage i.a. init, test case stages or finalize
        #ended with non-zero status code 
        self.failed = False
    #---------------------------------------------------------------------------
    def addCaseRun(self, tc):
        '''
        @param tc: TestCase object
        '''
        tc.uid = tc.name + '-' + datetime.datetime.now().isoformat()
        tc.uid = tc.uid.translate(maketrans('', ''), '-:.') # remove special
                                                            # chars from uid
        tc.initDate = datetime.datetime.now()

        self.cases[tc.uid] = tc
        self.caseUidByName[tc.name] = tc.uid
    #---------------------------------------------------------------------------
    def addStageResult(self, state, result, uid=None, slave_name=None):
        '''
        @param state: state that happened
        @param result: result of test run (code, stdout, stderr)
        @param uid: uid of test case or test suite init/finalize
        @param slave_name: where stage ended
        '''
        state.time = state.datetime.strftime("%H:%M:%S, %d-%m-%Y")

        LOGGER.info("New stage result %s (ret code %s)" % \
                     (state, result[2]))
        LOGGER.debug("New stage result %s: (code %s) %s" % \
                    (state, result[2], result[0]))

        if result[2] != '0':
            self.failed = True

        if result[1] == None:
            result = (result[0], "", result[2])

        self.stagesResults.append((state, result, uid, slave_name))
    #--------------------------------------------------------------------------- 
    def getTestCaseStages(self, test_case_uid):
        stages = [v for v in \
                  self.stagesResults if v[2] == test_case_uid]
        return stages
#------------------------------------------------------------------------------ 
class Job(object):

    S_ADDED = (0, "Job added to jobs list.")
    S_STARTED = (1, "Job started. In progress.")

    INITIALIZE_TEST_SUITE = 1
    FINALIZE_TEST_SUITE = 2

    INITIALIZE_TEST_CASE = 3
    RUN_TEST_CASE = 4
    FINALIZE_TEST_CASE = 5

    START_CLUSTER = 6
    STOP_CLUSTER = 7

    def __init__(self, job, args=None):
        self.job = job
        self.state = Job.S_ADDED
        self.args = args
#-------------------------------------------------------------------------------
class ClustersDefinitionsChangeHandler(ProcessEvent):
    '''
    Clusters' definitions files change handler
    '''
    #---------------------------------------------------------------------------
    def __init__(self, pevent=None, **kwargs):
        ProcessEvent.__init__(self, pevent=pevent, **kwargs)
        self.callback = kwargs['masterCallback']
    #---------------------------------------------------------------------------
    def process_default(self, event):
        self.callback("CLUSTER", event)
#-------------------------------------------------------------------------------
class SuitsDefinitionsChangeHandler(ProcessEvent):
    '''
    Suits' definitions files change handler
    '''
    #---------------------------------------------------------------------------
    def __init__(self, pevent=None, **kwargs):
        ProcessEvent.__init__(self, pevent=pevent, **kwargs)
        self.callback = kwargs['masterCallback']
    #---------------------------------------------------------------------------
    def process_default(self, event):
        self.callback("SUIT", event)
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
    # TestSuits that has ever run, synchronized with a HDD, key of dict is 
    # session.uid
    suitsSessions = None
    #---------------------------------------------------------------------------
    # Mapping from names to uids of running test suits. Useful for retrieval 
    # of test suit sessions saved in suitsSessions python shelve. 
    runningSuitsUids = {}
    #---------------------------------------------------------------------------
    # Definitions of clusters loaded from a file, keyed by name
    clusters = {}
    #---------------------------------------------------------------------------
    # Which hypervisor run the cluster. Key cluster.name, value hypervisor
    clustersHypervisor = {}

    #---------------------------------------------------------------------------
    # Definitions of test suits loaded from file
    testSuits = {}
    #---------------------------------------------------------------------------
    # Constants
    C_SLAVE = 'slave'
    C_HYPERV = 'hypervisor'
    #---------------------------------------------------------------------------
    # Jobs to run immediately if possible. They are put here by scheduler.
    pendingJobs = []
    #---------------------------------------------------------------------------
    # Jobs to run immediately if possible. They are put here by scheduler.
    # Queue for DEBUGGING
    pendingJobsDbg = []
    #---------------------------------------------------------------------------
    # message logging system
    userMsgs = []
    #---------------------------------------------------------------------------
    # tasks scheduler instance
    sched = Scheduler()
    #---------------------------------------------------------------------------
    def __init__(self, config):
        self.config = config
        self.suitsSessions = shelve.open(\
                             self.config.get('tests', 'suits_sessions_file'))
    #---------------------------------------------------------------------------
    def retrieveSuiteSession(self, suite_name):
        return self.suitsSessions[self.runningSuitsUids[suite_name]]
    #---------------------------------------------------------------------------
    def storeSuiteSession(self, test_suite_session):
        self.runningSuitsUids[test_suite_session.name] = test_suite_session.uid
        self.suitsSessions[test_suite_session.uid] = test_suite_session
        self.suitsSessions.sync()
    #---------------------------------------------------------------------------
    def fireReloadDefinitionsEvent(self, type, dirEvent):
        evt = None
        if type == "CLUSTER":
            evt = MasterEvent(MasterEvent.M_RELOAD_CLUSTER_DEF, dirEvent)
        if type == "SUIT":
            evt = MasterEvent(MasterEvent.M_RELOAD_SUIT_DEF, dirEvent)
        self.recvQueue.put((MasterEvent.PRIO_IMPORTANT, evt))
    #---------------------------------------------------------------------------
    def loadDefinitions(self):
        LOGGER.info("Loading definitions...")

        try:
            clusters = loadClustersDefs(\
                        self.config.get('server', 'clusters_definition_path'))
            for clu in clusters:
                self.clusters[clu.name] = clu
        except ClusterManagerException, e:
            LOGGER.error("ClusterManager Exception: %s" % e)
            sys.exit()

        try:
            testSuits = loadTestSuitsDefs(\
                        self.config.get('server', 'testsuits_definition_path'))
            for ts in testSuits.itervalues():
                ts.checkIfDefComplete(self.clusters)
            self.testSuits = testSuits
        except TestSuiteException, e:
            LOGGER.error("Test Suite Exception: %s" % e)
            sys.exit()

        if self.config.getint('scheduler', 'enabled') == 1:
            for ts in self.testSuits.itervalues():
                if not ts.schedule:
                    continue
                try:
                    ts.jobFun = self.executeJob(ts.name)
                    self.sched.add_cron_job(ts.jobFun, \
                                             **(ts.schedule))

                    LOGGER.info("Adding scheduler job for test suite %s at %s" % \
                                (ts.name, str(ts.schedule)))
                except Exception, e:
                    LOGGER.error(("Error while scheduling job " + \
                               "for test suite %s: %s") % (ts.name, e))
                    sys.exit()
    #---------------------------------------------------------------------------
    def handleSuiteDefinitionChanged(self, dirEvent):
        p = os.path.join(dirEvent.path, dirEvent.name)
        (modName, ext, modPath, modFile) = extractSuiteName(p)

        if ext != ".py":
            return

        LOGGER.info("Suit def changed (%s) in %s" % (dirEvent.maskname, p))

        remMasks = ["IN_DELETE", "IN_MOVED_FROM"]
        addMasks = ["IN_CREATE", "IN_MOVED_TO"]

        #TODO it may couse inconsistency in suits defs
        if dirEvent.maskname in remMasks or \
            dirEvent.maskname == "IN_MODIFY":
            try:
                LOGGER.info("Undefining test suite: %s" % modName)
                if not self.testSuits.has_key(modName):
                    raise TestSuiteException(("There is no test suite " + \
                                             "%s defined.") % (modName))
                self.sched.unschedule_func(self.testSuits[modName].jobFun)
                del sys.modules[modName]
                del self.testSuits[modName]
                del modName
            except TestSuiteException, e:
                LOGGER.error("Error while undefining: %s" % e)
        if dirEvent.maskname in addMasks or \
            dirEvent.maskname == "IN_MODIFY":
            try:
                suite = loadTestSuiteDef(p)
                try:
                    if suite:
                        suite.checkIfDefComplete(self.clusters)
                except TestSuiteException, e:
                    LOGGER.error("Definition warning: %s." % e)
                if suite:
                    self.testSuits[suite.name] = suite
                    self.testSuits[suite.name].jobFun = self.executeJob(suite.name)
                    self.sched.add_cron_job(self.testSuits[suite.name].jobFun, \
                                             **(suite.schedule))
            except TestSuiteException, e:
                LOGGER.error("Error while defining: %s" % e)
            except Exception, e:
                LOGGER.info(("Error while defining " + \
                            " test suite %s") % e)
    #---------------------------------------------------------------------------
    def checkIfSuitsDefsComplete(self):
        for ts in self.testSuits.values():
            ts.checkIfDefComplete(self.clusters)
    #---------------------------------------------------------------------------
    def handleClusterDefinitionChanged(self, dirEvent):
        p = os.path.join(dirEvent.path, dirEvent.name)
        (modName, ext, modPath, modFile) = extractClusterName(p)

        if ext != ".py":
            return

        LOGGER.info("Cluster def changed (%s) in %s: " % (dirEvent.maskname, p))

        remMasks = ["IN_DELETE", "IN_MOVED_FROM"]
        addMasks = ["IN_CREATE", "IN_MOVED_TO"]

        if dirEvent.maskname in remMasks or \
            dirEvent.maskname == "IN_MODIFY":
            try:
                LOGGER.info("Undefining cluster: %s" % modName)
                del sys.modules[modName]
                del self.clusters[modName]
                del modName
                self.checkIfSuitsDefsComplete()
            except ClusterManagerException, e:
                LOGGER.error("Error while undefining: %s" % e)
        if dirEvent.maskname in addMasks or \
            dirEvent.maskname == "IN_MODIFY":
            try:
                clu = loadClusterDef(p, self.clusters.values(), True)
                LOGGER.info("Defining cluster: %s" % clu.name)
                self.clusters[clu.name] = clu
                self.checkIfSuitsDefsComplete()
            except ClusterManagerException, e:
                LOGGER.error("Error while defining: %s" % e)
    #---------------------------------------------------------------------------
    def slaveState(self, slave_name):
        '''
        Get state of a slave, even if not connected.
        @param slave_name: equal to full hostname
        '''
        key = [k for k, v in self.slaves.iteritems() \
               if slave_name == v.hostname]
        ret = State(TCPClient.S_NOT_CONNECTED)
        if len(key):
            key = key[0]
        if key:
            ret = self.slaves[key].state
        return ret
    #---------------------------------------------------------------------------
    def getSuiteSlaves(self, test_suite, slave_state=None, test_case=None):
        '''
        Gets reference to currently connected slaves required by test_suite.
        Optionally return only slaves with state slave_state.
        @param test_suite: test suite definition
        @param slave_state: required slave state
        '''
        cond_ts = lambda v: (v.hostname in test_suite.machines)

        if not test_case or (test_case and not test_case.machines):
            cond_tc = lambda v: True
        else:
            cond_tc = lambda v: (v.hostname in test_case.machines)

        cond_state = lambda v: True
        if not slave_state:
            pass
        elif slave_state == State(Slave.S_SUIT_INITIALIZED):
            cond_state = lambda v: \
                        (self.slaveState(v.hostname) == slave_state and \
                         v.state.suiteName == test_suite.name)
        elif slave_state:
            cond_state = lambda v: \
                        (self.slaveState(v.hostname) == slave_state)
        else:
            pass

        cond = lambda v: cond_ts(v) and cond_tc(v) and cond_state(v)

        testSlaves = [v for v in self.slaves.itervalues() if cond(v)]

        return testSlaves
    #---------------------------------------------------------------------------
    def startCluster(self, clusterName, maintenance=False):
        clusterFound = False
        if self.clusters.has_key(clusterName):
            if self.clusters[clusterName].name == clusterName:
                clusterFound = True
                #@todo: choosing hypervisor in more intelligent
                #choose one Hipervisor arbitrarily
                if len(self.hypervisors):
                    msg = XrdMessage(XrdMessage.M_START_CLUSTER)
                    msg.clusterDef = self.clusters[clusterName]
                    msg.maintenance = maintenance

                    #take first possible hypervisor and send him cluster def
                    hyperv = [h for h in self.hypervisors.itervalues()][0]
                    hyperv.send(msg)

                    self.clusters[clusterName].state = \
                        State(Cluster.S_DEFINITION_SENT)
                    self.clustersHypervisor[clusterName] = hyperv

                    LOGGER.info("Cluster start command sent to %s", hyperv)
                    return True
                else:
                    LOGGER.warning("No hypervisor to run the cluster on")
                    self.clusters[clusterName].state = \
                        State(Cluster.S_UNKNOWN_NOHYPERV)
                    return False
        if not clusterFound:
            LOGGER.error("No cluster with name " + str(clusterName) + " found")
            return False
    #---------------------------------------------------------------------------
    def stopCluster(self, clusterName, maintenance=False):
        clusterFound = False
        if self.clusters.has_key(clusterName):
            if self.clusters[clusterName].name == clusterName:
                clusterFound = True
                if self.clusters[clusterName].state != State(Cluster.S_ACTIVE):
                    LOGGER.error("Cluster is not active so it can't be stopped")
                    return

                msg = XrdMessage(XrdMessage.M_STOP_CLUSTER)
                msg.clusterDef = self.clusters[clusterName]
                msg.maintenance = maintenance

                hyperv = self.clustersHypervisor[clusterName]
                hyperv.send(msg)

                self.clusters[clusterName].state = \
                    State(Cluster.S_STOPCOMMAND_SENT)

                LOGGER.info("Cluster stop command sent to %s", hyperv)
                return True
            return False
        if not clusterFound:
            LOGGER.error("No cluster with name " + str(clusterName) + " found")
            return False
    #---------------------------------------------------------------------------
    def initializeTestSuite(self, test_suite_name):
        '''
        Sends initialize message to slaves, creates TestSuite Session
        and stores it at HDD.
        @param test_suite_name:
        '''
        # filling test suite machines automatically if user
        # provided none
        testSuite = self.testSuits[test_suite_name]

        if not testSuite.defComplete:
            LOGGER.info("Test suite definition is not complete, " + \
                        " some clusters need to be defined.")
            return False

        unreadyMachines = []
        for m in testSuite.machines:
            if self.slaveState(m) != State(Slave.S_CONNECTED_IDLE):
                unreadyMachines.append(m)
                LOGGER.debug("Can't init %s because %s not ready or busy." % \
                               (test_suite_name, m))

        if len(unreadyMachines):
            LOGGER.debug("Some required machines are not " + \
                         "ready for the test suite: %s" % str(unreadyMachines))
            return False

        testSlaves = self.getSuiteSlaves(testSuite)

        tss = TestSuiteSession(testSuite)
        tss.state = State(TestSuite.S_WAIT_4_INIT)

        self.storeSuiteSession(tss)

        msg = XrdMessage(XrdMessage.M_TESTSUITE_INIT)
        msg.suiteName = tss.name
        msg.cmd = tss.suite.initialize

        #@todo:  if sending to some machines fails 
        #        initialization on rest should be reversed
        for sl in testSlaves:
            LOGGER.info("Sending Test Suite initialize to %s" % sl)
            sl.send(msg)
            sl.state = State(Slave.S_SUITINIT_SENT)

        return True
    #---------------------------------------------------------------------------
    def finalizeTestSuite(self, test_suite_name):
        '''
        Sends finalization message to slaves and destroys TestSuiteSession.
        @param test_suite_name:
        '''
        if not self.runningSuitsUids.has_key(test_suite_name):
            LOGGER.debug("TestSuite has not been initialized.")
            return False

        tss = self.retrieveSuiteSession(test_suite_name)

        if not tss.state == State(TestSuite.S_ALL_INITIALIZED):
            LOGGER.debug("TestSuite not yet initialized.")
            return False

        unreadyMachines = []
        for m in tss.suite.machines:
            if self.slaveState(m) != State(Slave.S_SUIT_INITIALIZED):
                unreadyMachines.append(m)
                LOGGER.debug(m + " state " + str(self.slaveState(m)))

        if len(unreadyMachines):
            LOGGER.debug("Some required machines are not " + \
                         " ready for the finalize: %s" % str(unreadyMachines))
            return False

        msg = XrdMessage(XrdMessage.M_TESTSUITE_FINALIZE)
        msg.suiteName = tss.name
        msg.cmd = tss.suite.finalize

        tSlaves = self.getSuiteSlaves(tss.suite)
        for sl in tSlaves:
            LOGGER.debug("Sending Test Suite finalize to %s" % sl)
            sl.send(msg)
            sl.state = State(Slave.S_SUITFINALIZE_SENT)
            sl.state.sessUid = tss.uid

        tss.state = State(TestSuite.S_WAIT_4_FINALIZE)

        return True
    #---------------------------------------------------------------------------
    def initializeTestCase(self, test_suite_name, test_name):
        '''
        Sends initTest message to slaves.
        @param test_suite_name:
        @param test_name:
        '''
        # Checks if we already initialized suite
        if not self.runningSuitsUids.has_key(test_suite_name):
            LOGGER.debug("Test Suite %s has not been initialized." % \
                            test_suite_name)
            return False

        tss = self.retrieveSuiteSession(test_suite_name)
        if not tss.state == State(TestSuite.S_ALL_INITIALIZED):
            LOGGER.debug("TestSuite %s machines have not been initialized" % \
                           test_suite_name)
            return False

        # copy test case to test suite session context
        tc = deepcopy(tss.suite.testCases[test_name])
        tss.addCaseRun(tc)

        msg = XrdMessage(XrdMessage.M_TESTCASE_INIT)
        msg.suiteName = test_suite_name
        msg.testName = test_name
        msg.testUid = tc.uid
        msg.case = tc

        testSlaves = self.getSuiteSlaves(tss.suite, test_case=tc)

        for sl in testSlaves:
            LOGGER.debug("Sending %s %s to %s" % (msg.name, test_name, sl))
            sl.send(msg)
            sl.state = State(Slave.S_TEST_INIT_SENT)

        tss.state = State(TestSuite.S_WAIT_4_TEST_INIT)
        self.storeSuiteSession(tss)

        return True
    #---------------------------------------------------------------------------
    def runTestCase(self, test_suite_name, test_name):
        '''
        Sends runTest message to slaves.
        @param test_suite_name:
        @param test_name:
        '''
        # Checks if we already initialized suite
        if not self.runningSuitsUids.has_key(test_suite_name):
            LOGGER.debug("Test Suite %s has not been initialized." % \
                            test_suite_name)
            return False

        tss = self.retrieveSuiteSession(test_suite_name)
        if not tss.state == State(TestSuite.S_ALL_TEST_INITIALIZED):
            LOGGER.debug("TestSuite %s machines have not initialized test" % \
                           test_suite_name)
            return False

        testUid = tss.caseUidByName[test_name]
        tc = tss.cases[testUid]

        msg = XrdMessage(XrdMessage.M_TESTCASE_RUN)
        msg.suiteName = test_suite_name
        msg.testName = tc.name
        msg.testUid = tc.uid

        testSlaves = self.getSuiteSlaves(tss.suite, test_case=tc)

        for sl in testSlaves:
            LOGGER.debug("Sending %s %s to %s" % (msg.name, tc.name, sl))
            sl.send(msg)
            sl.state = State(Slave.S_TEST_RUN_SENT)

        tss.state = State(TestSuite.S_WAIT_4_TEST_RUN)
        self.storeSuiteSession(tss)

        return True
    #---------------------------------------------------------------------------
    def finalizeTestCase(self, test_suite_name, test_name):
        '''
        Sends runTest message to slaves.
        @param test_suite_name:
        @param test_name:
        '''
        # Checks if we already initialized suite
        if not self.runningSuitsUids.has_key(test_suite_name):
            LOGGER.debug("Test Suite %s has not been initialized." % \
                            test_suite_name)
            return False

        tss = self.retrieveSuiteSession(test_suite_name)
        if not tss.state == State(TestSuite.S_ALL_TEST_RUN_FINISHED):
            LOGGER.debug("TestSuite %s machines have not run finished" % \
                           test_suite_name)
            return False

        testUid = tss.caseUidByName[test_name]
        tc = tss.cases[testUid]

        msg = XrdMessage(XrdMessage.M_TESTCASE_FINALIZE)
        msg.suiteName = test_suite_name
        msg.testName = tc.name
        msg.testUid = tc.uid

        testSlaves = self.getSuiteSlaves(tss.suite, test_case=tc)

        for sl in testSlaves:
            LOGGER.debug("Sending %s %s to %s" % (msg.name, tc.name, sl))
            sl.send(msg)
            sl.state = State(Slave.S_TEST_FINALIZE_SENT)

        tss.state = State(TestSuite.S_WAIT_4_TEST_FINALIZE)
        self.storeSuiteSession(tss)

        return True
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
    def fireEnqueueJobEvent(self, test_suite_name):
        '''
        Add the Run Job event to main events queue of controll thread.
        @param test_suite_name:
        '''
        evt = MasterEvent(MasterEvent.M_JOB_ENQUEUE, test_suite_name)
        self.recvQueue.put((MasterEvent.PRIO_NORMAL, evt))
        #---------------------------------------------------------------------------
    def executeJob(self, test_suite_name):
        '''
        Closure for fireEnqueueJobEvent to hold the test_suite_name 
        argument for execution.
        @param test_suite_name: name of test suite
        '''
        return lambda: self.fireEnqueueJobEvent(test_suite_name)
    #---------------------------------------------------------------------------
    def enqueueJob(self, test_suite_name):
        '''
        Add job to list of running jobs and initiate its run.
        @param test_suite_name:
        '''
        LOGGER.info("runJob for testsuite %s " % test_suite_name)

        ts = self.testSuits[test_suite_name]
        for clustName in ts.clusters:
            j = Job(Job.START_CLUSTER, clustName)
            self.pendingJobs.append(j)
            self.pendingJobsDbg.append("startCluster(%s)" % clustName)

        j = Job(Job.INITIALIZE_TEST_SUITE, test_suite_name)
        self.pendingJobs.append(j)
        self.pendingJobsDbg.append("initSuite(%s)" % test_suite_name)

        for tName in ts.tests:
            j = Job(Job.INITIALIZE_TEST_CASE, (test_suite_name, tName))
            self.pendingJobs.append(j)
            self.pendingJobsDbg.append("initTest(%s)" % tName)

            j = Job(Job.RUN_TEST_CASE, (test_suite_name, tName))
            self.pendingJobs.append(j)
            self.pendingJobsDbg.append("runTest(%s)" % tName)

            j = Job(Job.FINALIZE_TEST_CASE, (test_suite_name, tName))
            self.pendingJobs.append(j)
            self.pendingJobsDbg.append("finalizeTest(%s)" % tName)

        j = Job(Job.FINALIZE_TEST_SUITE, test_suite_name)
        self.pendingJobs.append(j)
        self.pendingJobsDbg.append("finalizeSuite(%s)" % test_suite_name)

        for clustName in ts.clusters:
            j = Job(Job.STOP_CLUSTER, clustName)
            self.pendingJobs.append(j)
            self.pendingJobsDbg.append("stopCluster(%s)" % clustName)

    #---------------------------------------------------------------------------
    def startJobs(self):
        '''
        Look through queue of jobs and start one, who have conditions.
        @param test_suite_name:
        '''
        if len(self.pendingJobsDbg) <= 7:
            LOGGER.info("PENDING JOBS %s " % self.pendingJobsDbg)
        else:
            LOGGER.info("PENDING JOBS (next 7) %s " % self.pendingJobsDbg[:7])

        LOGGER.info("startJobs() pending: %s " % len(self.pendingJobs))
        if len(self.pendingJobs) > 0:
            j = self.pendingJobs[0]
            #LOGGER.info("JOB: %s, %s, %s" % (j.job, j.state, j.args))
            if not j.state == Job.S_STARTED:
                if j.job == Job.INITIALIZE_TEST_SUITE:
                    if self.initializeTestSuite(j.args):
                        self.pendingJobs[0].state = Job.S_STARTED
                elif j.job == Job.FINALIZE_TEST_SUITE:
                    if self.finalizeTestSuite(j.args):
                        self.pendingJobs[0].state = Job.S_STARTED

                elif j.job == Job.INITIALIZE_TEST_CASE:
                    if self.initializeTestCase(j.args[0], j.args[1]):
                        self.pendingJobs[0].state = Job.S_STARTED
                elif j.job == Job.RUN_TEST_CASE:
                    if self.runTestCase(j.args[0], j.args[1]):
                        self.pendingJobs[0].state = Job.S_STARTED
                elif j.job == Job.FINALIZE_TEST_CASE:
                    if self.finalizeTestCase(j.args[0], j.args[1]):
                        self.pendingJobs[0].state = Job.S_STARTED

                elif j.job == Job.START_CLUSTER:
                    if self.startCluster(j.args):
                        self.pendingJobs[0].state = Job.S_STARTED
                elif j.job == Job.STOP_CLUSTER:
                    if len(self.pendingJobs) > 1:
                        nj = self.pendingJobs[1]
                        if nj and nj.job == Job.START_CLUSTER and \
                            nj.args == j.args:
                            self.pendingJobs = self.pendingJobs[2:]
                            self.pendingJobsDbg = self.pendingJobsDbg[2:]
                            self.startJobs()
                            return

                    if self.stopCluster(j.args):
                        self.pendingJobs[0].state = Job.S_STARTED
                else:
                    LOGGER.error("Job %s unrecognized" % j.job)
    #---------------------------------------------------------------------------
    def removeJob(self, removeJob):
        '''
        Look through queue of jobs and start one, who have conditions.
        @param test_suite_name:
        '''
        if len(self.pendingJobs):
            j = self.pendingJobs[0]
            if j.state == Job.S_STARTED:
                if j.job == removeJob.job and j.args == removeJob.args:
                    self.pendingJobs = self.pendingJobs[1:]
                    self.pendingJobsDbg = self.pendingJobsDbg[1:]
                    LOGGER.info("Removing job %s", j.job)
    #---------------------------------------------------------------------------
    def procSlaveMsg(self, msg):
        if msg.name == XrdMessage.M_TESTSUITE_STATE:
            slave = self.slaves[msg.sender]

            if msg.state == State(TestSuite.S_SLAVE_INITIALIZED):
                slave.state = State(Slave.S_SUIT_INITIALIZED)
                slave.state.suiteName = msg.suiteName

                tss = self.retrieveSuiteSession(msg.suiteName)
                tss.addStageResult(msg.state, msg.result,
                                   uid="suite_inited",
                                   slave_name=slave.hostname)
                #update SuiteStatus if all slaves are inited
                iSlaves = self.getSuiteSlaves(tss.suite,
                                        State(Slave.S_SUIT_INITIALIZED))
                LOGGER.info("%s initialized in test suite %s" % \
                            (slave, tss.name))
                if len(iSlaves) == len(tss.suite.machines):
                    tss.state = State(TestSuite.S_ALL_INITIALIZED)
                    self.removeJob(Job(Job.INITIALIZE_TEST_SUITE, \
                                       args=tss.name))
                    LOGGER.info("All slaves initialized in " + \
                                " test suite %s" % tss.name)
                self.storeSuiteSession(tss)
            elif msg.state == State(TestSuite.S_SLAVE_FINALIZED):
                tss = self.retrieveSuiteSession(msg.suiteName)
                slave.state = State(Slave.S_CONNECTED_IDLE)
                tss.addStageResult(msg.state, msg.result,
                                   uid="suite_finalized",
                                   slave_name=slave.hostname)

                iSlaves = self.getSuiteSlaves(tss.suite, \
                                            State(Slave.S_CONNECTED_IDLE))

                if len(iSlaves) >= len(tss.suite.machines):
                    tss.state = State(TestSuite.S_ALL_FINALIZED)
                    self.removeJob(Job(Job.FINALIZE_TEST_SUITE, \
                                       args=tss.name))
                    del self.runningSuitsUids[tss.name]

                self.storeSuiteSession(tss)
                LOGGER.info("%s finalized in test suite: %s" % \
                            (slave, tss.name))
            elif msg.state == State(TestSuite.S_SLAVE_TEST_INITIALIZED):
                tss = self.retrieveSuiteSession(msg.suiteName)
                tss.addStageResult(msg.state, msg.result, uid=msg.testUid,
                                   slave_name=slave.hostname)

                slave.state = State(Slave.S_TEST_INITIALIZED)
                tc = tss.cases[msg.testUid]
                waitSlaves = self.getSuiteSlaves(tss.suite, test_case=tc)
                readySlaves = self.getSuiteSlaves(tss.suite, \
                                            State(Slave.S_TEST_INITIALIZED),
                                            test_case=tc)
                if len(waitSlaves) == len(readySlaves):
                    tss.state = State(TestSuite.S_ALL_TEST_INITIALIZED)
                    self.removeJob(Job(Job.INITIALIZE_TEST_CASE, \
                                       args=(tss.name, tc.name)))
                self.storeSuiteSession(tss)
                LOGGER.info("%s initialized test %s in suite %s" % \
                            (slave, msg.testName, tss.name))
            elif msg.state == State(TestSuite.S_SLAVE_TEST_RUN_FINISHED):
                tss = self.retrieveSuiteSession(msg.suiteName)
                tss.addStageResult(msg.state, msg.result,
                                   slave_name=slave.hostname,
                                   uid=msg.testUid)
                slave.state = State(Slave.S_TEST_RUN_FINISHED)
                tc = tss.cases[msg.testUid]
                waitSlaves = self.getSuiteSlaves(tss.suite, test_case=tc)
                readySlaves = self.getSuiteSlaves(tss.suite, \
                                            State(Slave.S_TEST_RUN_FINISHED),
                                            test_case=tc)
                if len(waitSlaves) == len(readySlaves):
                    tss.state = State(TestSuite.S_ALL_TEST_RUN_FINISHED)
                    self.removeJob(Job(Job.RUN_TEST_CASE, \
                                       args=(tss.name, tc.name)))
                self.storeSuiteSession(tss)
                LOGGER.info("%s finished run test %s in suite %s" % \
                            (slave, msg.testName, tss.name))
            elif msg.state == State(TestSuite.S_SLAVE_TEST_FINALIZED):
                tss = self.retrieveSuiteSession(msg.suiteName)
                tss.addStageResult(msg.state, msg.result, \
                                   slave_name=slave.hostname, \
                                   uid=msg.testUid)
                slave.state = State(Slave.S_SUIT_INITIALIZED)
                slave.state.suiteName = msg.suiteName

                tc = tss.cases[msg.testUid]
                waitSlaves = self.getSuiteSlaves(tss.suite, test_case=tc)
                readySlaves = self.getSuiteSlaves(tss.suite, \
                                            State(Slave.S_SUIT_INITIALIZED),
                                            test_case=tc)
                if len(waitSlaves) == len(readySlaves):
                    tss.state = State(TestSuite.S_ALL_INITIALIZED)
                    self.removeJob(Job(Job.FINALIZE_TEST_CASE, \
                                       args=(tss.name, tc.name)))
                self.storeSuiteSession(tss)
                LOGGER.info("%s finalized test %s in suite %s" % \
                            (slave, msg.testName, tss.name))
    #---------------------------------------------------------------------------
    def procEvents(self):
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
                        if msg.state == State(Cluster.S_ACTIVE):
                            self.removeJob(Job(Job.START_CLUSTER, \
                                               args=msg.clusterName))
                        elif msg.state == State(Cluster.S_STOPPED):
                            self.removeJob(Job(Job.STOP_CLUSTER, \
                                               args=msg.clusterName))
                    else:
                        raise XrdTestMasterException("Unknown cluster " + \
                                                     "state recvd: " + \
                                                     msg.clusterName)
            #-------------------------------------------------------------------
            # Messages from slaves
            elif evt.type == MasterEvent.M_SLAVE_MSG:
                msg = evt.data
                self.procSlaveMsg(msg)
            #------------------------------------------------------------------- 
            elif evt.type == MasterEvent.M_JOB_ENQUEUE:
                self.enqueueJob(evt.data)
            #------------------------------------------------------------------- 
            elif evt.type == MasterEvent.M_RELOAD_CLUSTER_DEF:
                self.handleClusterDefinitionChanged(evt.data)
            #------------------------------------------------------------------- 
            elif evt.type == MasterEvent.M_RELOAD_SUIT_DEF:
                self.handleSuiteDefinitionChanged(evt.data)
            #-------------------------------------------------------------------
            else:
                raise XrdTestMasterException("Unknown incoming evt type " + \
                                             str(evt.type))
            self.startJobs()
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

        if self.config.getint('scheduler', 'enabled') == 1:
            #-------------------------------------------------------------------
            # Enable scheduler
            self.sched.start()
        else:
            LOGGER.info("SCHEDULER is disabled.")

        self.loadDefinitions()
        #-----------------------------------------------------------------------
        # schedule config reloading job
#        self.sched.add_cron_job(self.fireReloadDefinitionsEvent, \
#                           minute=self.config.get('server', \
#                           'definitions_reload_minute'))

        #-----------------------------------------------------------------------
        # NOTIFYING FOR DEFINITIONS CHANGE SETUP
        wm = WatchManager()
        wm2 = WatchManager()
        # constants from /usr/src/linux/include/linux/inotify.h
        IN_MOVED = 0x00000040L | 0x00000080L     # File was moved to or from X
        IN_CREATE = 0x00000100L     # Subfile was created
        IN_DELETE = 0x00000200L     # was delete
        IN_MODIFY = 0x00000002L     # was modified
        mask = IN_DELETE | IN_CREATE | IN_MOVED | IN_MODIFY
        clustersNotifier = ThreadedNotifier(wm, \
                            ClustersDefinitionsChangeHandler(\
                            masterCallback=self.fireReloadDefinitionsEvent))
        suitsNotifier = ThreadedNotifier(wm2, \
                            SuitsDefinitionsChangeHandler(\
                            masterCallback=self.fireReloadDefinitionsEvent))
        clustersNotifier.start()
        suitsNotifier.start()

        wddc = wm.add_watch(self.config.get('server', \
                           'clusters_definition_path'), \
                           mask, rec=True)
        wdds = wm2.add_watch(self.config.get('server', \
                           'testsuits_definition_path'), \
                           mask, rec=True)

        cherrypyCfg = {
                    '/webpage/js': {
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
        self.procEvents()
        #-----------------------------------------------------------------------
        # synchronize suits sessions list with HDD storage and close
        clustersNotifier.stop()
        suitsNotifier.stop()
        xrdTestMaster.suitsSessions.close()
#-------------------------------------------------------------------------------
class UserInfoHandler(logging.Handler):
    '''
    Specialized logging handler, to show logging messages in Web Interface
    '''
    testMaster = None
    def __init__(self, xrdTestMaster):
            logging.Handler.__init__(self)
            self.testMaster = xrdTestMaster
    def emit(self, record):
        self.testMaster.userMsgs.append(record)

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
            LOGGER.exception(str(e))
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
        LOGGER.error("OS Error occured %s" % e)
        sys.exit(1)

