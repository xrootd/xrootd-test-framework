#!/usr/bin/env python
#-------------------------------------------------------------------------------
#
# Copyright (c) 2011-2012 by European Organization for Nuclear Research (CERN)
# Author: Lukasz Trzaska <ltrzaska@cern.ch>
#
# This file is part of XrdTest.
#
# XrdTest is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# XrdTest is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with XrdTest.  If not, see <http://www.gnu.org/licenses/>.
#
#-------------------------------------------------------------------------------
#
# File:    XrdTestMaster
# Desc:    Xroot Testing Framework main module.
#          * user entry point to the framework
#          * supervise and synchronise all system activities
#          * accepts connections from Slaves and Hypervisors and dispatches 
#            commands to them
#          * is run as a system service, configured via batch of config files
#
#-------------------------------------------------------------------------------
from XrdTest.Utils import Logger
LOGGER = Logger(__name__).setup()

try:
    import logging
    import sys
    import ConfigParser
    import random
    import os
    import socket
    import threading
    import shelve
    import cherrypy
    import re
    
    from XrdTest.ClusterUtils import ClusterManagerException, extractClusterName, \
        loadClusterDef, loadClustersDefs, Cluster 
    from XrdTest.SocketUtils import XrdMessage, PriorityBlockingQueue
    from XrdTest.TCPServer import MasterEvent, ThreadedTCPRequestHandler, \
        ThreadedTCPServer
    from XrdTest.TCPClient import TCPClient, Hypervisor, Slave
    from XrdTest.TestUtils import TestSuiteException, TestSuite, TestSuiteSession, \
        loadTestSuiteDef, loadTestSuiteDefs, extractSuiteName
    from XrdTest.Job import Job
    from XrdTest.Daemon import Runnable, Daemon, DaemonException
    from XrdTest.Utils import State, redirectOutput, Command
    from XrdTest.GitUtils import sync_remote_git
    from XrdTest.WebInterface import WebInterface
    from XrdTest.DirectoryWatch import DirectoryWatch
    from apscheduler.scheduler import Scheduler
    from copy import deepcopy, copy
    from optparse import OptionParser
    from datetime import datetime, timedelta
except ImportError, e:
    LOGGER.error(str(e))
    sys.exit(1)


class XrdTestMasterException(Exception):
    '''
    General Exception raised by XrdTestMaster.
    '''
    def __init__(self, desc):
        '''
        Constructs Exception
        @param desc: description of an error
        '''
        self.desc = desc
        
    def __str__(self):
        '''
        Returns textual representation of an error
        '''
        return repr(self.desc)


class XrdTestMaster(Runnable):
    '''
    Main class of module, only one instance can exist in the system,
    it's runnable as a daemon.
    '''
    def __init__(self, configFile, backgroundMode):
        # Global configuration for master
        self.config = None 
        # Default daemon configuration
        self.defaultConfFile = '/etc/XrdTest/XrdTestMaster.conf'
        self.defaultPidFile = '/var/run/XrdTestMaster.pid'
        self.defaultLogFile = '/var/log/XrdTest/XrdTestMaster.log'
        # Must be a string, as config file param is a string - getattr() 
        # will get proper int val later
        self.logLevel = 'INFO'
        
        # Default TCP server configuration
        self.serverIP = '0.0.0.0'
        self.serverPort = 20000
        
        # Priority queue (locking) with incoming events, i.a. incoming messages
        # Referred to as: main events queue.
        self.recvQueue = PriorityBlockingQueue()
        # Connected hypervisors, keys: address tuple, values: Hypervisor object
        self.hypervisors = {}
        # Connected slaves, keys: address tuple, values: Slave object
        self.slaves = {}
        # TestSuites that have ever run, synchronized with a HDD, key is session.uid
        self.suiteSessions = None
        # Currently running test suite object, if any.
        self.runningSuite = None
        # Mapping from names to uids of running test suits. For retrieval of 
        # TestSuiteSessions saved in suiteSessions python shelve. 
        self.runningSuiteUids = {}
        # Definitions of clusters loaded from a file, key is cluster.name
        # Refreshed any time definitions change.
        self.clusters = {}
        # Which hypervisor run given cluster. Key: cluster.name Value: Hypervisor
        # object
        self.clustersHypervisor = {}
        # Definitions of test suits loaded from file. Key: testSuite.name 
        # Value: testSuite.definition. Refreshed any time definitions chagne.
        self.testSuites = {}
        # Definitions of all directories being monitored for changes.
        self.watchedDirectories = {}
        # Jobs to run immediately if possible. They are put here by scheduler.
        self.pendingJobs = []
        # The same as above, for debugging. Keeps textual representation of jobs.
        self.pendingJobsDbg = []
        # message logging system
        self.userMsgs = []
        # tasks scheduler only instance
        self.sched = None
        # Constants
        self.C_SLAVE = 'slave'
        self.C_HYPERV = 'hypervisor'
        
        if not configFile:
            configFile = self.defaultConfFile
        self.config = self.readConfig(configFile)
        
        # setup logging level
        if self.config.has_option('daemon', 'log_level'):
            self.logLevel = self.config.get('daemon', 'log_level')
        logging.getLogger().setLevel(getattr(logging, self.logLevel))
            
        # redirect output on daemon start
        if backgroundMode:
            if self.config.has_option('daemon', 'log_file_path'):
                redirectOutput(self.config.get('daemon', 'log_file_path'))
        
        LOGGER.info("Using config file: %s" % configFile)
        
        self.loadSuiteSessions()
            
    def loadSuiteSessions(self):
        if self.config.has_option('general', 'suite_sessions_file'):
                self.suiteSessions = shelve.open(\
                             self.config.get('general', 'suite_sessions_file'))
        else:
            LOGGER.error('Cannot open suite session storage file.')

    def archiveSuiteSessions(self):
        self.suiteSessions.sync()
        self.suiteSessions.close()
        
        active = self.config.get('general', 'suite_sessions_file')
        
        archive = '%s.%s' % (active, datetime.now().strftime('%d%m%y-%H%M%S'))
        os.rename(active, archive)
        
        self.suiteSessions = shelve.open(active)
        
    def retrieveSuiteSession(self, suite_name):
        '''
        Retrieve test suite session from shelve self.suiteSessions
        @param suite_name:
        '''
        if self.runningSuiteUids.has_key(suite_name) and \
            self.suiteSessions.has_key(self.runningSuiteUids[suite_name]):
            return self.suiteSessions[self.runningSuiteUids[suite_name]]
        else:
            return None
    
    def retrieveAllSuiteSessions(self):
        all = {}
        
        active = self.config.get('general', 'suite_sessions_file')
        path = os.sep.join(active.split(os.sep)[:-1])
        prefix = active.split(os.sep)[-1:][0]
        
        for f in os.listdir(path):
            if f.startswith(prefix):
                s = shelve.open(os.path.join(path, f))
                all.update({f:s})
        
        return all

    def storeSuiteSession(self, test_suite_session):
        '''
        Save test suite session to python shelve self.suiteSessions
        @param test_suite_session:
        '''
        print len(self.suiteSessions)
        if len(self.suiteSessions) > 30:
            self.archiveSuiteSessions()
            
        self.runningSuiteUids[test_suite_session.name] = test_suite_session.uid
        self.suiteSessions[test_suite_session.uid] = test_suite_session
        self.suiteSessions.sync()

    def fireReloadDefinitionsEvent(self, type, dirEvent=None):
        '''
        Any time something is changed in the directory with config files,
        it puts proper event into main events queue.
        @param type:
        @param dirEvent:
        '''
        evt = None
        if type == "CLUSTER":
            evt = MasterEvent(MasterEvent.M_RELOAD_CLUSTER_DEF, dirEvent)
        if type == "SUITE":
            evt = MasterEvent(MasterEvent.M_RELOAD_SUITE_DEF, dirEvent)
        self.recvQueue.put((MasterEvent.PRIO_IMPORTANT, evt))

    def loadDefinitions(self):
        '''
        Load all definitions of example clusters and test suites at once.
        If any definitions are invalid, raise exceptions.
        '''
        LOGGER.info("Loading definitions...")

        for repo in map(lambda x: x.strip(), filter(lambda x: x, self.config.get('general', 'test-repos').split(','))): 
            repo = 'test-repo-' + repo
            LOGGER.info('Setting up repository %s' % repo)
            
            # Pull remote git repo if necessary
            if self.config.get(repo, 'type') == 'git':
                sync_remote_git(repo, self.config)
                
            if self.config.has_option(repo, 'local_path'):
                localPath = self.config.get(repo, 'local_path')
                LOGGER.info('Using local path %s for test repository %s' % (localPath, repo))
            else:
                LOGGER.error('No local path defined for repository %s' % repo) 
            
            try:
                # load cluster definitions
                if self.config.has_option(repo, 'cluster_defs_path'):
                    clustDefPath = os.path.join(localPath, self.config.get(repo, 'cluster_defs_path'))
                elif os.path.exists(os.path.join(localPath, 'clusters')):
                    clustDefPath = os.path.join(localPath, 'clusters')
                else:
                    LOGGER.error('No cluster definitions found for repository %s' % repo)
                    
                clusters = loadClustersDefs(clustDefPath)
                for clu in clusters:
                    self.clusters[clu.name] = clu
            except ClusterManagerException, e:
                LOGGER.error("ClusterManager Exception: %s" % e)
    
            try:
                # load test suite definitions
                if self.config.has_option(repo, 'suite_defs_path'):
                    suiteDefPath = os.path.join(localPath, self.config.get(repo, 'suite_defs_path'))
                elif os.path.exists(os.path.join(localPath, 'test-suites')):
                    suiteDefPath = os.path.join(localPath, 'test-suites')
                else:
                    LOGGER.error('No test suite definitions found for repository %s' % repo)
                
                testSuites = loadTestSuiteDefs(suiteDefPath)
                for ts in testSuites:
                    try:
                        ts.checkIfDefComplete(self.clusters)
                    except TestSuiteException, e:
                        ts.state = State((-1, e.desc))
                    self.testSuites[ts.name] = ts
            except TestSuiteException, e:
                LOGGER.error("Test Suite Exception: %s" % e)
                suite = TestSuite()
                suite.name = ts.name
                suite.state = State((-1, e.desc))
                self.testSuites[suite.name] = suite
    
            # add jobs to scheduler if it's enabled
            if self.config.getint('scheduler', 'enabled') == 1:
                for ts in self.testSuites.itervalues():
                    # if there is no scheduling expression defined in suite, continue
                    if not ts.schedule:
                        continue
                    try:
                        ts.jobFun = self.executeJob(ts.name)
                        ts.job = self.sched.add_cron_job(ts.jobFun, \
                                                 **(ts.schedule))
    
                        LOGGER.info("Adding scheduler job for test suite %s at %s" % \
                                    (ts.name, str(ts.schedule)))
                    except Exception, e:
                        LOGGER.error(("Error while scheduling job " + \
                                   "for test suite %s: %s") % (ts.name, e))

    def handleSuiteDefinitionChanged(self, dirEvent):
        '''
        Handle event created any time definition of test suite changes.
        @param dirEvent:
        '''
        p = os.path.join(dirEvent.path, dirEvent.name)
        
        # The APScheduler event masks are highly unreliable. Also, we might want
        # to have a definition reloaded when a change is made to a non-uniquely
        # named file, such as suite_init.sh. So, when a change is detected, 
        # all definitions are reloaded from scratch.
        
        LOGGER.info("Suite definition changed (%s) in %s" % (dirEvent.maskname, p))
        
        for ts in self.testSuites.itervalues():
            if ts.jobFun:
                self.sched.unschedule_func(ts.jobFun)
                
        self.testSuites = dict()
        
        self.loadDefinitions()
        
        
#        (modName, ext, modPath, modFile) = extractSuiteName(p)
#
#        if ext != ".py":
#            return
#
#        LOGGER.info("Suit def changed (%s) in %s" % (dirEvent.maskname, p))
#
#        remMasks = ["IN_DELETE", "IN_MOVED_FROM"]
#        addMasks = ["IN_CREATE", "IN_MOVED_TO"]
#
#        # if removed of modified do tasks necessary while removing job
#        if dirEvent.maskname in remMasks or dirEvent.maskname == "IN_MODIFY":
#            try:
#                LOGGER.info("Undefining test suite: %s" % modName)
#                if self.testSuites.has_key(modName):
#                    # unschedule job connected to this test suite
#                    if self.testSuites[modName].jobFun:
#                        self.sched.unschedule_func(\
#                                                self.testSuites[modName].jobFun)
#                    # remove module from imports
#                    del sys.modules[modName]
#                    # remove testSuite from test suits' definitions
#                    del self.testSuites[modName]
#            except TestSuiteException, e:
#                LOGGER.error("Error while undefining: %s" % str(e))
#            except Exception, e:
#                LOGGER.error(("Error while defining test suite %s") % e)
#
#        #if file added or modified do tasks necessary while adding jobs 
#        if dirEvent.maskname in addMasks or \
#            dirEvent.maskname == "IN_MODIFY":
#            try:
#                # load single test suite definition
#                LOGGER.info("Defining test suite: %s" % modName)
#                suite = loadTestSuiteDef(p)
#                if suite:
#                    suite.checkIfDefComplete(self.clusters)
#                    suite.state = State(TestSuite.S_DEF_OK)
#                    # add job connected to added test suite
#                    suite.jobFun = self.executeJob(suite.name)
#                    self.sched.add_cron_job(suite.jobFun, **(suite.schedule))
#                    self.testSuites[suite.name] = suite
#            except TestSuiteException, e:
#                LOGGER.error("Error while defining: %s" % e)
#                suite = TestSuite()
#                suite.name = modName
#                suite.state = State((-1, e.desc))
#                self.testSuites[suite.name] = suite
#            except Exception, e:
#                # in case of any exception thron e.g. from scheduler
#                LOGGER.error(("Error while defining " + \
#                            " test suite %s") % e)

    def checkIfSuitsDefsComplete(self):
        '''
        Search for incompletness in test suits' definitions, that may be caused
        by e.g. lack of test case definition.
        @param dirEvent:
        '''
        try:
            for ts in self.testSuites.values():
                ts.checkIfDefComplete(self.clusters)
        except TestSuiteException, e:
            raise TestSuiteException("Error in test suite %s: %s." % (ts.name, e))
        except Exception, e:
            raise TestSuiteException("Error in test suite %s: %s." % (ts.name, e))

    def handleClusterDefinitionChanged(self, dirEvent):
        '''
        Handle event created any time definition of cluster changes.
        @param dirEvent:
        '''
        p = os.path.join(dirEvent.path, dirEvent.name)
        
        LOGGER.info("Cluster definition changed (%s) in %s: " % (dirEvent.maskname, p))
        
        self.clusters = dict()
        self.loadDefinitions()
        
        
#        (modName, ext, modPath, modFile) = extractClusterName(p)
#
#        if ext != ".py":
#            return
#
#        LOGGER.info("Cluster def changed (%s) in %s: " % (dirEvent.maskname, p))
#
#        remMasks = ["IN_DELETE", "IN_MOVED_FROM"]
#        addMasks = ["IN_CREATE", "IN_MOVED_TO"]
#
#        # cluster definition removed or modified (same things in both cases)
#        if dirEvent.maskname in remMasks or dirEvent.maskname == "IN_MODIFY":
#            try:
#                LOGGER.info("Undefining cluster: %s" % modName)
#                if self.clusters.has_key(modName):
#                    # remove module from imports
#                    del sys.modules[modName]
#                    # remove cluster definition
#                    del self.clusters[modName]
#                # check if after deletion all test suits definitions are valid
#                self.checkIfSuitsDefsComplete()
#            except TestSuiteException, e:
#                LOGGER.error("Error while undefining: %s" % e)
#                for ts in self.testSuites.itervalues():
#                    if modName in ts.clusters:
#                        ts.state = State((-1, e.desc))
#            except ClusterManagerException, e:
#                LOGGER.error("Error while undefining: %s" % e)
#        # cluster definition added or modified (same things in both cases)
#        if dirEvent.maskname in addMasks or dirEvent.maskname == "IN_MODIFY":
#            try:
#                LOGGER.info("Defining cluster: %s" % modName)
#                clu = loadClusterDef(p, self.clusters.values(), True)
#                self.clusters[clu.name] = clu
#                # check if after adding some test suits definitions become valid
#                self.checkIfSuitsDefsComplete()
#            except (TestSuiteException, ClusterManagerException), e:
#                LOGGER.error("Error while defining: %s" % e)
#                clu = Cluster()
#                clu.name = modName
#                clu.state = State((-1, e.desc))
#                self.clusters[clu.name] = clu


    def slaveState(self, slave_name):
        '''
        Get state of a slave by its name, even if it's not connected.
        @param slave_name: equal to fully qualified hostname
        '''
        key = [k for k, v in self.slaves.iteritems() \
               if slave_name == v.hostname]
        ret = State(TCPClient.S_NOT_CONNECTED)
        if len(key):
            key = key[0]
        if key:
            ret = self.slaves[key].state
        return ret

    def getSuiteSlaves(self, test_suite, slave_state=None, test_case=None):
        '''
        Gets reference to slaves' objects representing slaves currently
        connected. Optionally return only slaves associated with the given
        test_suite or test_case
        or being in given slave_state. All given parameters has to accord.
        @param test_suite: test suite definition
        @param slave_state: required slave state
        @param test_case: test case defintion
        '''
        cond_ts = lambda v: (v.hostname in test_suite.machines)

        if not test_case or (test_case and not test_case.machines):
            cond_tc = lambda v: True
        else:
            cond_tc = lambda v: (v.hostname in test_case.machines)

        cond_state = lambda v: True
        if not slave_state:
            pass
        elif slave_state == State(Slave.S_SUITE_INITIALIZED):
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

    def startCluster(self, clusterName, suiteName, jobGroupId):
        '''
        Sends message to hypervisor to start the cluster.

        @param clusterName:
        @param suiteName:
        @param jobGroupId:
        @return: True/False in case of Success/Failure in sending messages
        '''
        testSuite = self.testSuites[suiteName]
        tss = TestSuiteSession(testSuite)
        tss.state = State(TestSuite.S_IDLE)
        self.storeSuiteSession(tss)
        
        # Set one hour timeout
        # TODO: make timeout value configurable per-suite
        self.sched.add_date_job(self.cancelTestSuite,
                           datetime.now() + timedelta(hours=1),
                           [suiteName, True])
        self.runningSuite = tss
        
        clusterFound = False
        if self.clusters.has_key(clusterName):
            if self.clusters[clusterName].name == clusterName:
                clusterFound = True
                #@todo: choosing hypervisor in more intelligent
                #choose one Hipervisor arbitrarily
                if len(self.hypervisors):
                    msg = XrdMessage(XrdMessage.M_START_CLUSTER)
                    msg.clusterDef = self.clusters[clusterName]
                    msg.jobGroupId = jobGroupId
                    msg.suiteName = suiteName

                    #take random hypervisor and send him cluster def
                    hNum = random.randint(0, len(self.hypervisors) - 1)
                    hyperv = [h for h in self.hypervisors.itervalues()][hNum]
                    hyperv.send(msg)

                    self.clusters[clusterName].state = \
                        State(Cluster.S_DEFINITION_SENT)
                    self.clustersHypervisor[clusterName] = hyperv
                    hyperv.runningClusterDefs[clusterName] = \
                                            copy(self.clusters[clusterName])

                    LOGGER.info("Cluster start command sent to %s", hyperv)
                    return True
                else:
                    LOGGER.warning("No hypervisor to run the cluster %s on" % \
                                   clusterName)
                    self.clusters[clusterName].state = \
                        State(Cluster.S_UNKNOWN_NOHYPERV)
                    return False
        if not clusterFound:
            LOGGER.error("No cluster with name " + str(clusterName) + " found")
            return False

    def stopCluster(self, clusterName):
        '''
        Sends message to hypervisor to stop the cluster.

        @param clusterName:
        @return: True/False in case of Success/Failure in sending messages
        '''
        clusterFound = False
        if self.clusters.has_key(clusterName):
            if self.clusters[clusterName].name == clusterName:
                clusterFound = True
#                if self.clusters[clusterName].state != State(Cluster.S_ACTIVE):
#                    LOGGER.error("Cluster is not active so it can't be stopped")
#                    return

                msg = XrdMessage(XrdMessage.M_STOP_CLUSTER)
                hyperv = self.clustersHypervisor[clusterName]
                msg.clusterDef = hyperv.runningClusterDefs[clusterName]
                hyperv.send(msg)

                self.clusters[clusterName].state = \
                    State(Cluster.S_STOPCOMMAND_SENT)

                LOGGER.info("Cluster stop command sent to %s", hyperv)
                
                # Cluster was stopped - remove all slaves.
                self.slaves = {}
                                
                # Remove timeout job. If we get here because a timeout job fired,
                # then the job will have been unscheduled automatically.
                try:
                    self.sched.unschedule_func(self.cancelTestSuite)
                except:
                    pass
                
                return True
            return False
        if not clusterFound:
            LOGGER.error("No cluster with name " + str(clusterName) + " found")
            return False

    def initializeTestSuite(self, test_suite_name, jobGroupId):
        '''
        Sends initialize message to slaves, creates TestSuite Session
        and stores it in python shelve.

        @param test_suite_name:
        @param jobGroupId:
        @return: True/False in case of Success/Failure in sending messages
        '''
        # filling test suite machines automatically if user
        # provided none
        testSuite = self.testSuites[test_suite_name]

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
        
        # If we are here, the cluster must be active, i.e. all slaves are
        # connected to the master.
        for cluster in self.testSuites[test_suite_name].clusters:
            self.clusters[cluster].state = State(Cluster.S_ACTIVE)
        
        testSlaves = self.getSuiteSlaves(testSuite)

        tss = self.retrieveSuiteSession(test_suite_name)
        tss.state = State(TestSuite.S_WAIT_4_INIT)
        self.storeSuiteSession(tss)

        msg = XrdMessage(XrdMessage.M_TESTSUITE_INIT)
        msg.suiteName = tss.name
        msg.cmd = tss.suite.initialize
        msg.jobGroupId = jobGroupId

        # TODO:  if sending to some machines fails,
        # initialization on rest should be reversed
        for sl in testSlaves:
            LOGGER.info("Sending Test Suite initialize to %s" % sl)
            sl.send(msg)
            sl.state = State(Slave.S_SUITE_INIT_SENT)

        return True

    def finalizeTestSuite(self, test_suite_name):
        '''
        Sends finalization message to slaves and destroys TestSuiteSession.

        @param test_suite_name:
        @return: True/False in case of Success/Failure in sending messages
        '''
        if not self.runningSuiteUids.has_key(test_suite_name):
            LOGGER.debug("TestSuite has not been initialized.")
            return False

        tss = self.retrieveSuiteSession(test_suite_name)

        if not tss.state in (State(TestSuite.S_ALL_INITIALIZED), \
                             State(TestSuite.S_ALL_TEST_FINALIZED)):
            LOGGER.debug("TestSuite not yet initialized.")
            return False

        unreadyMachines = []
        for m in tss.suite.machines:
            if self.slaveState(m) != State(Slave.S_SUITE_INITIALIZED):
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
            sl.state = State(Slave.S_SUITE_FINALIZE_SENT)
            sl.state.sessUid = tss.uid

        tss.state = State(TestSuite.S_WAIT_4_FINALIZE)

        return True

    def initializeTestCase(self, test_suite_name, test_name, jobGroupId):
        '''
        Sends initTest message to slaves.

        @param test_suite_name:
        @param test_name:
        @param jobGroupId:
        @return: True/False in case of Success/Failure in sending messages
        '''
        # Checks if we already initialized suite
        if not self.runningSuiteUids.has_key(test_suite_name):
            LOGGER.debug("Test Suite %s has not been initialized." % \
                            test_suite_name)
            return False

        tss = self.retrieveSuiteSession(test_suite_name)
        if not tss.state in (State(TestSuite.S_ALL_INITIALIZED), \
                             State(TestSuite.S_ALL_TEST_FINALIZED)):
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
        msg.jobGroupId = jobGroupId

        testSlaves = self.getSuiteSlaves(tss.suite, test_case=tc)

        for sl in testSlaves:
            LOGGER.debug("Sending %s %s to %s" % (msg.name, test_name, sl))
            sl.send(msg)
            sl.state = State(Slave.S_TEST_INIT_SENT)

        tss.state = State(TestSuite.S_WAIT_4_TEST_INIT)
        self.storeSuiteSession(tss)

        return True

    def runTestCase(self, test_suite_name, test_name):
        '''
        Sends runTest message to slaves.

        @param test_suite_name:
        @param test_name:
        @return: True/False in case of Success/Failure in sending messages
        '''
        # Checks if we already initialized suite
        if not self.runningSuiteUids.has_key(test_suite_name):
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

    def finalizeTestCase(self, test_suite_name, test_name):
        '''
        Sends runTest message to slaves.

        @param test_suite_name:
        @param test_name:
        @return: True/False in case of Success/Failure in sending messages
        '''
        # Checks if we already initialized suite
        if not self.runningSuiteUids.has_key(test_suite_name):
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

    def handleClientConnected(self, client_type, client_addr, \
                              sock_obj, client_hostname):
        '''
        Do the logic of client incoming connection.

        @param client_type:
        @param client_addr:
        @param client_hostname:
        @return: None
        '''
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
            # TODO: disconnect client and end its thread
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
            
            for cluster in self.clusters.itervalues():
                if cluster.state == Cluster.S_UNKNOWN_NOHYPERV:
                    cluster.state = State(Cluster.S_DEFINED)
            
            if len(self.pendingJobs):
                self.startNextJob()

    def handleClientDisconnected(self, client_type, client_addr):
        '''
        Do the logic of client disconnection.

        @param client_type:
        @param client_addr:
        @return: None
        '''
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

    def fireEnqueueJobEvent(self, test_suite_name):
        '''
        Add the Run Job event to main events queue of controll thread.
        Method to be used by different thread.

        @param test_suite_name:
        @return: None
        '''
        evt = MasterEvent(MasterEvent.M_JOB_ENQUEUE, test_suite_name)
        self.recvQueue.put((MasterEvent.PRIO_NORMAL, evt))
        
    def runTestSuite(self, test_suite_name):
        '''Run a particular test suite '''
        self.enqueueJob(test_suite_name)
        self.startNextJob()
    
    def cancelTestSuite(self, test_suite_name, timeout=False):
        '''Cancel a running test suite '''
        if len(self.pendingJobs):
            # Remove the suite's jobs from the queue.
            job = self.pendingJobs[0]
            self.removeJobs(job.groupId)
            
            # Remove this run from the history, unless it timed out
            if timeout:
                LOGGER.warning('Test suite %s timed out ' % test_suite_name)
                if self.runningSuite and self.suiteSessions.has_key(self.runningSuite.uid):
                    tss = self.suiteSessions[self.runningSuite.uid]
                    tss.timeout = True
                    tss.failed = True
                    self.suiteSessions[self.runningSuite.uid] = tss
                self.suiteSessions.sync()
                
            elif self.runningSuite and self.suiteSessions.has_key(self.runningSuite.uid):
                del self.suiteSessions[self.runningSuite.uid]
                self.suiteSessions.sync()
            
            # Stop this suite's clusters.
            for cluster in self.testSuites[test_suite_name].clusters:
                if self.clustersHypervisor.has_key(cluster):
                    self.stopCluster(cluster)
                    
        if self.runningSuite and self.runningSuite.name == test_suite_name:
            self.runningSuite = None
                

    def executeJob(self, test_suite_name):
        '''
        Closure to pass the contexts of method self.fireEnqueueJobEvent:
        argument the test_suite_name.

        @param test_suite_name: name of test suite
        @return: lambda method with no argument
        '''
        return lambda: self.fireEnqueueJobEvent(test_suite_name)

    def enqueueJob(self, test_suite_name):
        '''
        Add job to list of jobs to run immediately after foregoing
        jobs are finished.

        @param test_suite_name:
        '''
        LOGGER.info("Enqueuing job for test suite: %s " % \
                     test_suite_name)

        groupId = Job.genJobGroupId(test_suite_name)

        try:
            ts = self.testSuites[test_suite_name]
        except KeyError, e:
            LOGGER.error('KeyError: %s is not a known test suite' % e)
            return 
        
        for clustName in ts.clusters:
            j = Job(Job.START_CLUSTER, groupId, (clustName, test_suite_name))
            self.pendingJobs.append(j)
            self.pendingJobsDbg.append("startCluster(%s)" % clustName)

        j = Job(Job.INITIALIZE_TEST_SUITE, groupId, test_suite_name)
        self.pendingJobs.append(j)
        self.pendingJobsDbg.append("initSuite(%s)" % test_suite_name)

        for tName in ts.tests:
            j = Job(Job.INITIALIZE_TEST_CASE, groupId, (test_suite_name, tName))
            self.pendingJobs.append(j)
            self.pendingJobsDbg.append("initTest(%s)" % tName)

            j = Job(Job.RUN_TEST_CASE, groupId, (test_suite_name, tName))
            self.pendingJobs.append(j)
            self.pendingJobsDbg.append("runTest(%s)" % tName)

            j = Job(Job.FINALIZE_TEST_CASE, groupId, (test_suite_name, tName))
            self.pendingJobs.append(j)
            self.pendingJobsDbg.append("finalizeTest(%s)" % tName)

        j = Job(Job.FINALIZE_TEST_SUITE, groupId, test_suite_name)
        self.pendingJobs.append(j)
        self.pendingJobsDbg.append("finalizeSuite(%s)" % test_suite_name)

        for clustName in ts.clusters:
            j = Job(Job.STOP_CLUSTER, groupId, clustName)
            self.pendingJobs.append(j)
            self.pendingJobsDbg.append("stopCluster(%s)" % clustName)

    def isJobValid(self, job):
        '''
        Check if job is still executable e.g. if required definitions
        are complete.

        @param job:
        @return: True/False
        '''
        if job.job == Job.INITIALIZE_TEST_SUITE:
            if not self.testSuites.has_key(job.args):
                return False
            elif not self.testSuites[job.args].defComplete:
                return False
            else:
                return True
        elif job.job == Job.START_CLUSTER:
            if not self.clusters.has_key(job.args[0]) or \
                self.clusters[job.args[0]].state.id < 0:
                return False
            elif not self.testSuites[job.args[1]].defComplete:
                return False
            else:
                return True

    def startNextJob(self):
        '''
        Start next possible job enqueued in pendingJobs list or continue
        without doing anything. Check if first job on a list is not already
        started, then check if it is valid and if it is, start it and change
        it's status to started.

        @param test_suite_name:
        @return: None
        '''
        # log next jobs that are pending
        if len(self.pendingJobsDbg) <= 7:
            LOGGER.info("PENDING JOBS[%s] %s " % (len(self.pendingJobs), \
                                                  self.pendingJobsDbg))
        else:
            LOGGER.info("PENDING JOBS[%s] (next 7) %s " % \
                                                    (len(self.pendingJobs),
                                                    self.pendingJobsDbg[:7]))
        if len(self.pendingJobs) > 0:
            j = self.pendingJobs[0]
            # if job is not already started, we can start it
            if not j.state == Job.S_STARTED:
                if j.job == Job.INITIALIZE_TEST_SUITE:
                    if self.isJobValid(j):
                        if self.initializeTestSuite(j.args, j.groupId):
                            self.pendingJobs[0].state = Job.S_STARTED
                        #else:
                        #    self.removeJobs(j.groupId)
                elif j.job == Job.FINALIZE_TEST_SUITE:
                    if self.finalizeTestSuite(j.args):
                        self.pendingJobs[0].state = Job.S_STARTED
                elif j.job == Job.INITIALIZE_TEST_CASE:
                    if self.initializeTestCase(j.args[0], j.args[1],
                                               j.groupId):
                        self.pendingJobs[0].state = Job.S_STARTED
                elif j.job == Job.RUN_TEST_CASE:
                    if self.runTestCase(j.args[0], j.args[1]):
                        self.pendingJobs[0].state = Job.S_STARTED
                elif j.job == Job.FINALIZE_TEST_CASE:
                    if self.finalizeTestCase(j.args[0], j.args[1]):
                        self.pendingJobs[0].state = Job.S_STARTED
                elif j.job == Job.START_CLUSTER:
                    if self.isJobValid(j):
                        if self.startCluster(j.args[0], j.args[1], j.groupId):
                            self.pendingJobs[0].state = Job.S_STARTED
                    else:
                        self.removeJobs(j.groupId)
                elif j.job == Job.STOP_CLUSTER:
                    #if next job is starting cluster, don't stop it. Save time.
                    if len(self.pendingJobs) > 1:
                        nj = self.pendingJobs[1]
                        if nj and nj.job == Job.START_CLUSTER and \
                            nj.args == j.args:
                            self.pendingJobs = self.pendingJobs[2:]
                            self.pendingJobsDbg = self.pendingJobsDbg[2:]
                            # self.startJobs()
                            return
                    if self.stopCluster(j.args):
                        self.pendingJobs[0].state = Job.S_STARTED
                else:
                    LOGGER.error("Job %s unrecognized" % j.job)

    def removeJobs(self, groupId, jobType=Job.START_CLUSTER, testName=None):
        '''
        Remove multiple jobs from enqueued jobs list. Depending of what kind of
        job is removed, different parameters are used and different number of
        jobs is removed.
        @param groupId: used for all kind of deleted jobs
        @param jobType: determines type of job that begins the chain of
                        jobs to be removed
        @param testName: used if removed jobs concerns particular test case
        @return: None
        '''
        newJobs = []
        newJobsDbg = []
        i = 0
        # condition checked on every element of jobs list
        # tell if job is to be removed 
        cond = lambda j: False
        cond1 = lambda j: (j.groupId == groupId)
        # remove jobs if test suite initialize failed
        if jobType == Job.INITIALIZE_TEST_SUITE:
            LOGGER.debug("Removing next few jobs due to suite initialize fail.")
            cond2 = lambda j: (j.job == Job.INITIALIZE_TEST_SUITE or \
                     j.job == Job.FINALIZE_TEST_SUITE or \
                     j.job == Job.INITIALIZE_TEST_CASE or \
                     j.job == Job.RUN_TEST_CASE or \
                     j.job == Job.FINALIZE_TEST_CASE)
            cond = lambda j: cond1(j) and cond2(j)
        # remove jobs if test case initialize failed
        elif jobType == Job.INITIALIZE_TEST_CASE:
            LOGGER.debug("Removing next few jobs due to test initialize fail.")
            cond2 = lambda j: (j.job == Job.INITIALIZE_TEST_CASE or \
                     j.job == Job.RUN_TEST_CASE or \
                     j.job == Job.FINALIZE_TEST_CASE)
            cond3 = lambda j: j.args[1] == testName
            cond = lambda j: cond1(j) and cond2(j) and cond3(j)
        # remove jobs if cluster start failed
        else:
            LOGGER.info("Removing next few jobs due to cluster start fail.")
            cond = lambda j: cond1(j)


        for j in self.pendingJobs:
            if cond(j):
                LOGGER.debug("Removing job %s" % self.pendingJobsDbg[i])
            else:
                newJobs.append(j)
                newJobsDbg.append(self.pendingJobsDbg[i])
            i += 1
        self.pendingJobs = newJobs
        self.pendingJobsDbg = newJobsDbg

    def removeJob(self, remove_job):
        '''
        Look through queue of jobs and remove one, which satisfy conditions
        defined by parameters of pattern job remove_job.

        @param remove_job: pattern of a job to be removed
        '''
        if len(self.pendingJobs):
            j = self.pendingJobs[0]
            if j.state == Job.S_STARTED:
                if j.job == remove_job.job and j.args == remove_job.args:
                    self.pendingJobs = self.pendingJobs[1:]
                    self.pendingJobsDbg = self.pendingJobsDbg[1:]

    def procSlaveMsg(self, msg):
        '''
        Process incoming messages from a slave.

        @param msg:
        '''
        # A slave is telling us the state of its test suite.
        if msg.name == XrdMessage.M_TESTSUITE_STATE:
            
            if not self.slaves.has_key(msg.sender):
                return
            
            slave = self.slaves[msg.sender]

            #===================================================================
            # Test suite was initialized on slave
            #===================================================================
            if msg.state == State(TestSuite.S_SLAVE_INITIALIZED):
                
                tss = self.retrieveSuiteSession(msg.suiteName)
                tss.addStageResult(msg.state, msg.result,
                                   uid="suite_inited",
                                   slave_name=slave.hostname)
                suiteInError = (tss.state == TestSuite.S_INIT_ERROR)

                # check if any errors occurred during init, 
                # if so release all slaves and remove proper pending jobs
                if msg.result[2] != "0":
                    # check if suite init error was already handled
                    if not suiteInError:
                        
                        tss.state = State(TestSuite.S_INIT_ERROR)
                        LOGGER.error("%s slave initialization error in test suite %s" \
                                     % (slave.hostname, tss.name))
                        LOGGER.error(msg.result)
                        
                        tss.sendEmailAlert(tss.failed, tss.state, tss.initDate, \
                                           result=msg.result[0], \
                                           slave_name=slave.hostname)
                        
                        # Set the state of all slaves to idle.
                        sSlaves = self.getSuiteSlaves(tss.suite)
                        for sSlave in sSlaves:
                            sSlave.state = State(Slave.S_CONNECTED_IDLE)

                        self.removeJobs(msg.jobGroupId, \
                                        Job.INITIALIZE_TEST_SUITE)
                        self.runningSuite = None
                
                # Init completed without error
                else:
                    slave.state = State(Slave.S_SUITE_INITIALIZED)
                    slave.state.suiteName = msg.suiteName
                    LOGGER.info("%s initialized in test suite %s" % \
                                (slave, tss.name))

                    # Are all slaves initialized? If so, remove the suite_init 
                    # job.
                    iSlaves = self.getSuiteSlaves(tss.suite,
                                            State(Slave.S_SUITE_INITIALIZED))
                    if len(iSlaves) == len(tss.suite.machines):
                        tss.state = State(TestSuite.S_ALL_INITIALIZED)
                        self.removeJob(Job(Job.INITIALIZE_TEST_SUITE, \
                                           args=tss.name))
                        LOGGER.info("All slaves initialized in " + \
                                    " test suite %s" % tss.name)
                        
                        tss.sendEmailAlert(msg.result[2], tss.state)
                        
                self.storeSuiteSession(tss)
            
            #===================================================================
            # Test suite was finalized on slave
            #===================================================================
            elif msg.state == State(TestSuite.S_SLAVE_FINALIZED):
                
                tss = self.retrieveSuiteSession(msg.suiteName)
                slave.state = State(Slave.S_CONNECTED_IDLE)
                LOGGER.info("%s finalized in test suite: %s" % \
                            (slave, tss.name))
                
                tss.addStageResult(msg.state, msg.result,
                                   uid="suite_finalized",
                                   slave_name=slave.hostname)
                
                tss.sendEmailAlert(msg.result[2], msg.state, \
                                   result=msg.result[0], \
                                   slave_name=slave.hostname)

                # Has the test suite been finalized on all slaves? If so,
                # remove the suite_finalize job.
                iSlaves = self.getSuiteSlaves(tss.suite, \
                                            State(Slave.S_CONNECTED_IDLE))
                if len(iSlaves) >= len(tss.suite.machines):
                    tss.state = State(TestSuite.S_ALL_FINALIZED)
                    
                    tss.sendEmailAlert(tss.failed, tss.state)
                    
                    self.removeJob(Job(Job.FINALIZE_TEST_SUITE, \
                                       args=tss.name))
                    # Suite has finished running, so unset these
                    del self.runningSuiteUids[tss.name]
                    self.runningSuite = None

                self.storeSuiteSession(tss)
                
            #===================================================================
            # Test case was initialized on slave
            #===================================================================
            elif msg.state == State(TestSuite.S_SLAVE_TEST_INITIALIZED):
                
                tss = self.retrieveSuiteSession(msg.suiteName)
                slave.state = State(Slave.S_TEST_INITIALIZED)
                LOGGER.info("%s initialized test %s in suite %s" % \
                            (slave, msg.testName, tss.name))
                
                tss.addStageResult(msg.state, msg.result, msg.testUid,
                       slave_name=slave.hostname)
                
                tc = tss.cases[msg.testUid]
                tss.sendEmailAlert(msg.result[2], msg.state, \
                                   result=msg.result[0], \
                                   slave_name=slave.hostname)
                                
                # Has the test case been initialized on all slaves? If so,
                # remove the case_init job.
                waitSlaves = self.getSuiteSlaves(tss.suite, test_case=tc)
                readySlaves = self.getSuiteSlaves(tss.suite, \
                                            State(Slave.S_TEST_INITIALIZED),
                                            test_case=tc)
                if len(waitSlaves) == len(readySlaves):
                    tss.state = State(TestSuite.S_ALL_TEST_INITIALIZED)
                    
                    self.removeJob(Job(Job.INITIALIZE_TEST_CASE, \
                                       args=(tss.name, tc.name)))
                
                self.storeSuiteSession(tss)
                
            
            #===================================================================
            # Test case finished running on slave
            #===================================================================
            elif msg.state == State(TestSuite.S_SLAVE_TEST_RUN_FINISHED):
                
                tss = self.retrieveSuiteSession(msg.suiteName)
                slave.state = State(Slave.S_TEST_RUN_FINISHED)
                LOGGER.info("%s finished run test %s in suite %s" % \
                            (slave, msg.testName, tss.name))
                
                tss.addStageResult(msg.state, msg.result,
                                   slave_name=slave.hostname,
                                   uid=msg.testUid)
                
                tc = tss.cases[msg.testUid]
                tss.sendEmailAlert(msg.result[2], msg.state, \
                                   result=msg.result[0], test_case=tc, \
                                   slave_name=slave.hostname)
                
                # Has the tast case finished running on all slaves? If so, 
                # remove the case_run job.
                waitSlaves = self.getSuiteSlaves(tss.suite, test_case=tc)
                readySlaves = self.getSuiteSlaves(tss.suite, \
                                            State(Slave.S_TEST_RUN_FINISHED),
                                            test_case=tc)
                if len(waitSlaves) == len(readySlaves):
                    tss.state = State(TestSuite.S_ALL_TEST_RUN_FINISHED)
                    
                    self.removeJob(Job(Job.RUN_TEST_CASE, \
                                       args=(tss.name, tc.name)))
                
                self.storeSuiteSession(tss)
                
            
            #===================================================================
            # Test case was finalized on slave
            #===================================================================
            elif msg.state == State(TestSuite.S_SLAVE_TEST_FINALIZED):
                
                tss = self.retrieveSuiteSession(msg.suiteName)
                slave.state = State(Slave.S_SUITE_INITIALIZED)
                slave.state.suiteName = msg.suiteName
                LOGGER.info("%s finalized test %s in suite %s" % \
                            (slave, msg.testName, tss.name))
                
                tss.addStageResult(msg.state, msg.result, \
                                   slave_name=slave.hostname, \
                                   uid=msg.testUid)
                
                tc = tss.cases[msg.testUid]
                tss.sendEmailAlert(msg.result[2], msg.state, \
                                   result=msg.result[0], test_case=tc)

                # Has the test case been finalized on all slaves? If so,
                # remove the case_finalize job.
                waitSlaves = self.getSuiteSlaves(tss.suite, test_case=tc)
                readySlaves = self.getSuiteSlaves(tss.suite, \
                                            State(Slave.S_SUITE_INITIALIZED),
                                            test_case=tc)
                if len(waitSlaves) == len(readySlaves):
                    tss.state = State(TestSuite.S_ALL_TEST_FINALIZED)
                    
                    tss.sendEmailAlert(tc.failed, tss.state, \
                                       test_case=tc)

                    self.removeJob(Job(Job.FINALIZE_TEST_CASE, \
                                       args=(tss.name, tc.name)))
                
                self.storeSuiteSession(tss)
                
        
        # A slave is requesting its specific script tags.
        elif msg.name == XrdMessage.M_TAG_REQUEST:
            slave = msg.hostname
            self.handleTagRequest(slave)
            
    def handleTagRequest(self, slavename):
        ''' TODO: '''
        for slave in self.slaves.itervalues():
            if slave.hostname == slavename:
                msg = XrdMessage(XrdMessage.M_TAG_REPLY)
                msg.proto = self.webInterface.protocol
                msg.port = self.webInterface.port
                
                # Find disk definitions
                disks = []
                for cluster in self.clusters.itervalues():
                    if cluster.state == Cluster.S_ACTIVE:
                        for host in cluster.hosts:
                            if host.name == slavename \
                            and host.clusterName == cluster.name:
                                disks = host.disks
                
                diskMountTemplate = '''
                    if [ ! -d %(mountpoint)s ]; then mkdir %(mountpoint)s; fi

                    mount -t ext4 -o user_xattr /dev/%(device)s %(mountpoint)s
                    chown $XROOTD_USER.$XROOTD_GROUP %(mountpoint)s
                    '''
                
                if len(disks):
                    msg.diskMounts = ''
                    for disk in disks:
                        values = dict()
                        values['mountpoint'] = disk.mountPoint
                        values['device'] = disk.device
                        msg.diskMounts += diskMountTemplate % values
                        
                # Add log file paths
                if self.runningSuite and self.testSuites.has_key(self.runningSuite.name):
                    msg.logFiles = self.testSuites[self.runningSuite.name].logs
                
                slave.send(msg)
        
    def procEvents(self):
        '''
        Main loop processing incoming MasterEvents from main events queue:
        self.recvQueue. MasterEvents with higher priority are handled first.
        '''
        while True:
            evt = self.recvQueue.get()

            if evt.type == MasterEvent.M_UNKNOWN:
                msg = evt.data
                LOGGER.debug("Received from [%s] %s" % (msg.sender, msg.name))

            # Event of client connect
            elif evt.type == MasterEvent.M_CLIENT_CONNECTED:
                self.handleClientConnected(evt.data[0], evt.data[1], \
                                           evt.data[2], evt.data[3])

            # Event of client disconnect
            elif evt.type == MasterEvent.M_CLIENT_DISCONNECTED:
                self.handleClientDisconnected(evt.data[0], evt.data[1])

            # Messages from hypervisors
            elif evt.type == MasterEvent.M_HYPERV_MSG:
                msg = evt.data
                if msg.name == XrdMessage.M_CLUSTER_STATE:
                    if self.clusters.has_key(msg.clusterName):
                        self.clusters[msg.clusterName].state = msg.state
                        LOGGER.info(("Cluster state received [%s] %s") % \
                                    (msg.clusterName, str(msg.state)))
                        if msg.state == Cluster.S_WAITING_SLAVES:
                            self.removeJob(Job(Job.START_CLUSTER, \
                                               args=(msg.clusterName,
                                                     msg.suiteName)))
                        elif msg.state == Cluster.S_ERROR_START:
                            LOGGER.error("Cluster error: %s" % msg.state)
                            self.removeJobs(msg.jobGroupId)
                        elif msg.state == State(Cluster.S_STOPPED):
                            self.removeJob(Job(Job.STOP_CLUSTER, \
                                               args=msg.clusterName))
                        elif msg.state == State(Cluster.S_ERROR_STOP):
                            LOGGER.error("Cluster error: %s" % msg.state)
                            self.removeJob(Job(Job.STOP_CLUSTER, \
                                               args=msg.clusterName))
                    else:
                        raise XrdTestMasterException("Unknown cluster " + \
                                                     "state received: " + \
                                                     msg.clusterName)
                
                elif msg.name == XrdMessage.M_HYPERVISOR_STATE:
                    if self.hypervisors.has_key(msg.sender):
                        self.hypervisors[msg.sender].states.append(msg.state)

            # Messages from slaves
            elif evt.type == MasterEvent.M_SLAVE_MSG:
                msg = evt.data
                self.procSlaveMsg(msg)

            # Messages from scheduler's threads
            elif evt.type == MasterEvent.M_JOB_ENQUEUE:
                self.enqueueJob(evt.data)

            # Messages from cluster definitions directory monitoring threads 
            elif evt.type == MasterEvent.M_RELOAD_CLUSTER_DEF:
                self.handleClusterDefinitionChanged(evt.data)

            # Messages from test suits definitions directory monitoring threads
            elif evt.type == MasterEvent.M_RELOAD_SUITE_DEF:
                self.handleSuiteDefinitionChanged(evt.data)

            # Incoming message is unknown
            else:
                raise XrdTestMasterException("Unknown incoming evt type " + \
                                             str(evt.type))

            # Event occurred in the system, so an opportunity might occur to
            # start next job
            self.startNextJob()

    def startTCPServer(self):
        '''
        TODO:
        '''
        if self.config.has_option('server', 'ip'):
            self.serverIP = self.config.get('server', 'ip')
                               
        if self.config.has_option('server', 'port'):
            self.serverPort = self.config.getint('server', 'port')

        try:
            server = ThreadedTCPServer((self.serverIP, self.serverPort),
                               ThreadedTCPRequestHandler)
        except socket.error, e:
            if e[0] == 98:
                LOGGER.info("Can't start server. Address already in use.")
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
        server_thread.daemon = True
        server_thread.start()
    
    def startWebInterface(self):
        '''
        TODO:
        '''
        webInterface = WebInterface(self.config, self)
        
        cherrypyCfg = {
                        '/webpage/js': {
                        'tools.staticdir.on': True,
                        'tools.staticdir.dir' : webInterface.webroot + "/js",
                        },
                        '/webpage/css': {
                        'tools.staticdir.on': True,
                        'tools.staticdir.dir' : webInterface.webroot + "/css",
                        },
                        '/webpage/img': {
                        'tools.staticdir.on': True,
                        'tools.staticdir.dir' : webInterface.webroot + "/img",
                        },
                       '/_static': {
                        'tools.staticdir.on': True,
                        'tools.staticdir.dir' : webInterface.webroot + "/docs/docs/build/html/_static",
                        },
                       '/': {
                        'tools.staticdir.on': True,
                        'tools.staticdir.dir' : webInterface.webroot + "/docs/docs/build/html/",
                        }
                       }
        
        cherrypy.tree.mount(webInterface, "/", cherrypyCfg)
            
        cherrypy.config.update({
                                'server.socket_host': self.serverIP,
                                'server.socket_port': webInterface.port,
                                'environment': 'production',
                                'log.screen': False,
                              })
    
        if webInterface.protocol == 'https':
            cherrypy.config.update({
                                    'server.ssl_module': 'pyopenssl'
                                  })
            
            if self.config.has_option('security', 'certfile'):
                cherrypy.config.update({'server.ssl_certificate': \
                                        self.config.get('security', 'certfile')})
            else:
                LOGGER.error('No SSL certificate defined in config file')
                
            if self.config.has_option('security', 'keyfile'):
                cherrypy.config.update({'server.ssl_private_key': \
                                        self.config.get('security', 'keyfile')})
            else:
                LOGGER.error('No SSL private key defined in config file')
    
        elif not webInterface.protocol == 'http':
            LOGGER.error('Unknown server protocol %s in config file' % webInterface.protocol)
            sys.exit(1)

        self.webInterface = webInterface
        try:
            cherrypy.server.start()
        except cherrypy._cperror.HTTPError, e:
            LOGGER.error(str(e))
            sys.exit(1)
        except socket.error, e:
            LOGGER.error(str(e))
            sys.exit(1)

        # Silence cherrypy and other unwanted logs
        loggers = LOGGER.manager.loggerDict.keys()
        for name in loggers:
            if re.match('(cherry|pyinotify|apscheduler)', name):
                logging.getLogger(name).setLevel(logging.ERROR)
                
    def createCA(self):
        '''Generate CA key/cert suitable for signing slave CSRs.'''
        ca_certfile = None
        ca_keyfile = None
        
        if self.config.has_option('security', 'ca_certfile'):
            ca_certfile = self.config.get('security', 'ca_certfile')
        else:
            LOGGER.error('No CA certificate defined in config file')
            
        if self.config.has_option('security', 'ca_keyfile'):
            ca_keyfile = self.config.get('security', 'ca_keyfile')
        else:
            LOGGER.error('No CA private key defined in config file')
        
        if not ca_certfile or not ca_keyfile:
            LOGGER.error('Master will not function properly as a CA. Test ' + \
                        'suites requiring signed GSI certs will fail.')
            return
        else:
            args = {'ca_certfile': ca_certfile, 'ca_keyfile': ca_keyfile}
        
        create_ca = \
        '''
CA_SUBJ="
C=CH
ST=Geneva
O=CERN
localityName=Geneva
commonName=ca.xrd.test CA
organizationalUnitName=Certificate Authority
emailAddress=ca@xrd.test"
            
# Generate the CA's private key/certificate
openssl genrsa -out %(ca_keyfile)s 4096
openssl req -new -batch -x509 \
        -subj "$(echo -n "$CA_SUBJ" | tr "\n" "/")" \
        -key %(ca_keyfile)s -out %(ca_certfile)s -days 1095
''' % args

        LOGGER.debug('Creating CA')
        Command(create_ca, '.').execute()

    def watchDirectories(self):
        '''
        TODO:
        '''
        for repo in map(lambda x: x.strip(), filter(lambda x: x, self.config.get('general', 'test-repos').split(','))):
            repo = 'test-repo-' + repo
            
            if self.config.get(repo, 'type') == 'localfs':
                self.watchedDirectories[repo] = DirectoryWatch(repo, self.config, \
                        self.fireReloadDefinitionsEvent, DirectoryWatch.watch_localfs)
            elif self.config.get(repo, 'type') == 'git':
                self.watchedDirectories[repo] = DirectoryWatch(repo, self.config, \
                        self.fireReloadDefinitionsEvent, DirectoryWatch.watch_remote_git)
            
            self.watchedDirectories[repo].watch()

    def run(self):
        '''
        Main method of a programme. Initializes all serving threads and starts
        main loop receiving MasterEvents.
        '''
        # Start TCP server for incoming slave and hypervisors connections
        self.startTCPServer()

        # Start scheduler if it's enabled in config file
        if self.config.getint('scheduler', 'enabled') == 1:
            LOGGER.info('Starting scheduler')
            self.sched = Scheduler()
            self.sched.start()
        else:
            LOGGER.info("SCHEDULER is disabled.")
            
        # Configure and start WWW Server - cherrypy
        self.startWebInterface()
        
        # Configure ourselves as a CA.
        self.createCA()
            
        # Load cluster and test suite definitions
        self.loadDefinitions()

        # Prepare notifiers for cluster and test suite definition 
        # directory monitoring (local and remote)
        self.watchDirectories()
        
        # Process events incoming to the system MasterEvents
        self.procEvents()

        # if here - program is ending
        for wd in self.watchedDirectories:
            wd.stop()
        # synchronize suits sessions list with HDD storage and close
        self.suiteSessions.close()

    def readConfig(self, confFile):
            '''
            Reads configuration from given file or from default if None given.
            @param confFile: file with configuration
            '''        
            config = ConfigParser.ConfigParser()
            if os.path.exists(confFile):
                try:
                    fp = file(confFile, 'r')
                    config.readfp(fp)
                    fp.close()
                except IOError, e:
                    LOGGER.exception(e)
            else:
                raise XrdTestMasterException("Config file %s could not be read" % confFile)
            return config
    
def main():
    '''
    Program begins here.
    '''
    parse = OptionParser()
    parse.add_option("-c", "--configfile", dest="configFile", type="string", \
                     action="store", help="config (.conf) file location")
    parse.add_option("-b", "--background", dest="backgroundMode", \
                     type='string', action="store", \
                      help="run runnable as a daemon")

    (options, args) = parse.parse_args()

    configFile = None
    if options.configFile:
        configFile = options.configFile

    # Initialize main class of the system
    xrdTestMaster = XrdTestMaster(configFile, options.backgroundMode)

    # run the daemon
    if options.backgroundMode:
        LOGGER.info("Run in background: %s" % options.backgroundMode)

        pidFile = xrdTestMaster.config.get('daemon', 'pid_file_path')
        logFile = xrdTestMaster.config.get('daemon', 'log_file_path')

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
            LOGGER.error(str(e))
            sys.exit(1)

    # run test master in standard mode. Used for debugging
    if not options.backgroundMode:
        xrdTestMaster.run()


if __name__ == '__main__':
    try:
        main()
    except OSError, e:
        LOGGER.error("OS Error occured %s" % e)
        sys.exit(1)
