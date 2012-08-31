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
# File:   TestUtils
# Desc:   General utilities for test suites and test cases.
# 
#        In all the scripts mentioned below, the string @slavename@ should be 
#        replaced with the actual machine name, so that the following statements 
#        are possible in the scripts:
#
#         if [ @slavename@ == machine1 ]; then
#           foo
#         elif [ @slavename@ == machine2 ]; then
#           bar
#         else
#           foobar
#         fi
#
#-------------------------------------------------------------------------------
from Utils import Logger
LOGGER = Logger(__name__).setup()

try:
    import os
    import sys
    import urllib2
    import datetime
    
    from Utils import State, Stateful
    from string import maketrans 
    from copy import deepcopy
except ImportError, e:
    LOGGER.error(str(e))
    sys.exit(1)

class TestSuiteException(Exception):
    '''
    General exception raised by module.
    '''
    ERR_UNKNOWN = 1
    ERR_CRITICAL = 2

    def __init__(self, desc, typeFlag=ERR_UNKNOWN):
        '''
        @param desc: description of an error
        @param typeFlag: represents type of an error, taken from class constants
        '''
        self.desc = desc
        self.type = typeFlag

    def __str__(self):
        '''
        Returns textual representation of an error
        '''
        return repr(self.desc)

class TestSuite(Stateful):
    '''
    Represents a single test suite object.
    '''
    S_DEF_OK = (1, "Test suite definition complete")
    
    S_IDLE = (10, "idle")

    S_WAIT_4_INIT = (20, "wait for suite initialization")
    S_SLAVE_INITIALIZED = (21, "slave initialized")
    S_ALL_INITIALIZED = (22, "all machines initialized")

    S_WAIT_4_FINALIZE = (30, "wait for suite finalization")
    S_SLAVE_FINALIZED = (31, "slave finalized")
    S_ALL_FINALIZED = (32, "all machines initialized")

    S_WAIT_4_TEST_INIT = (40, "sent test init")
    S_SLAVE_TEST_INITIALIZED = (41, "test initialized on a slave")
    S_ALL_TEST_INITIALIZED = (42, "test initialized on all slaves")

    S_WAIT_4_TEST_RUN = (43, "sent test to run")
    S_SLAVE_TEST_RUN_FINISHED = (44, "test run finished on a slave")
    S_ALL_TEST_RUN_FINISHED = (45, "test run finished on all slaves")

    S_WAIT_4_TEST_FINALIZE = (46, "send test to finalize")
    S_SLAVE_TEST_FINALIZED = (47, "test finalized on a slave")
    S_ALL_TEST_FINALIZED = (48, "test finalized on all slaves")

    S_INIT_ERROR = (-22, "initialization error")
    
    def __init__(self):
        Stateful.__init__(self)
        # Name of test suite: must be the same as the name of test suite definition 
        # file
        self.name = ""      
        # Name of test suite readable for humans, only for informational need
        self.descName = ""  
        # Define when the test should be run (cron style). Reference: APScheduler 
        # cronschedule
        self.schedule = {}             
        # A list of virtual clusters needed by the test to be spawned on a hypervisor
        self.clusters = []  
        # Names of machines, including the virtual machines that are needed by the 
        # test
        self.machines = []  
        # A URL to a shell script (starts with http://) or  a shell script (starts 
        # with #!) that defines the commands that need to be run on each test slave 
        # before any test case can run. If it fails then the entire test suite should 
        # be considered as failed.
        self.initialize = "" 
        # A URL to a shell script or a shell script that defines the clean up 
        # procedures to be run after all the tests cases are completed
        self.finalize = ""  
        # A list of test case names as defined below
        self.tests = []     

        # Fields beneath are filled automatically by system
        
        # Means that all cluster definitions that the cluster depends on are available
        self.defComplete = True 
        # Handle to function that will be used by scheduler. Has to be kept in case of
        # unscheduling.
        self.jobFun = None
        # Reference to the job object inside the scheduler
        self.job = None  
        # If machines were empty, system has to remember to reload them every time 
        # cluster definition changes
        self.machinesAutoFilled = False 
        # Filled automatically by load test suite defs. Holds Python objects 
        # representing test cases
        self.testCases = []    

        self.state = ''

    def validateStatic(self):
        '''
        Checks if definition (e.g given names) is statically correct.
        '''
        if not self.name or " " in self.name:
            raise TestSuiteException(("No name given for TestSuite, " + \
                                      "or the name (%s) " + \
                                      "is not alphanumeric without spaces.") % \
                                      self.name, \
                                      TestSuiteException.ERR_CRITICAL)
        if not self.schedule:
            raise TestSuiteException(("No scheduler expression " + \
                                      "given in TestSuite %s definition.") % \
                                      self.name, \
                                      TestSuiteException.ERR_CRITICAL)
        if not self.initialize:
            raise TestSuiteException(("No initialize script " + \
                                      "in TestSuite %s definition.") % \
                                      self.name, \
                                      TestSuiteException.ERR_CRITICAL)
        if not len(self.tests):
            raise TestSuiteException(("No test cases or no machines " + \
                                      "given in TestSuite %s definition.") % \
                                      self.name, \
                                      TestSuiteException.ERR_CRITICAL)
        for t in self.tests:
            if not self.testCases.has_key(t):
                raise TestSuiteException(("No TestCase %s was defined, but was used" + \
                                         " in TestSuite definition.") % str(t), \
                                          TestSuiteException.ERR_CRITICAL)
        return True

    def checkIfDefComplete(self, clusters):
        '''
        Makes sure all cluster definitions are complete.

        @param clusters: all currently defined clusters.
        '''
        if self.machinesAutoFilled:
            self.machines = []

        for cl in self.clusters:
            if not cl in clusters:
                self.defEnabled = False
                raise TestSuiteException(\
                ("Cluster %s in suite %s definition " + \
                "does not exist or is defined incorrectly.") % (cl, self.name))

        # check if all required machines are connected and idle
        if not len(self.machines):
            self.machinesAutoFilled = True
            for cName in self.clusters:
                self.machines.extend(\
                [h.name for h in clusters[cName].hosts])
                LOGGER.info(("Host list for suite %s " + \
                            "filled automatically with %s") % \
                            (self.name, self.machines))
                
    def getNextRunTime(self):
        '''Get the next scheduled run time for this suite.'''
        if self.job:
            return self.job.compute_next_run_time(datetime.datetime.now())
        else: return '-'
        
    def has_failure(self):
        return self.state.id < 0

class TestCase:
    '''
    Represents a single test case object.
    '''
    def __init__(self):
        # Name of the test case
        self.name = ""     
        # Names of the machines that the test case should run on. If empty, it 
        # runs on all machines in test suite
        self.machines = []  
        # A shell script or a link to a shell script that should be run on each 
        # machine. The initialize script should be completed on each machine 
        # before the run script can run. initialization failure is considered 
        # as a test case failure.
        self.initialize = ""
        # A shell script that is the actual test. If the script fails then the 
        # test case is considered as failed. The run scripts have to finish 
        # running on all the machines before the finalize script can be invoked.
        self.run = ""       
        # A script defining the finalization procedures
        self.finalize = "" 

        # Fields beneath are filled automatically by system
        
        # Keeps results of all test stages on machines. Index is a machine.
        self.resultsFromMachines = {}   
        self.uid = ""
        #filled with datetime.datetime.now()
        self.initDate = None

    def validateStatic(self):
        '''
        Return whether or not definition (e.g given names) is statically correct.
        '''
        if not self.name or " " in self.name:
            raise TestSuiteException(("No name given for TestCase, " + \
                                      "or the name (%s) " + \
                                      "is not alphanumeric without spaces.") % \
                                     self.name, \
                                      TestSuiteException.ERR_CRITICAL)
        return True


class TestSuiteSession(Stateful):
    '''
    Represents run of Test Suite from the moment of its initialization.
    It stores all information required for test suite to be run as well as
    results of test stages. It has unique id (uid parameter) for recognition,
    because there will be for sure many test suites with the same name.
    '''
    def __init__(self, suiteDef):
        Stateful.__init__(self)
        # name of test suite
        self.name = suiteDef.name
        # test suite definition copy
        self.suite = deepcopy(suiteDef)
        self.suite.jobFun = None
        # date of initialization
        self.initDate = datetime.datetime.now()
        # references to slaves who are necessary for the test suite
        self.slaves = []
        # keeps the results of each stage.
        self.stagesResults = []
        # unique identifier of test suite
        self.uid = self.suite.name + '-' + self.initDate.isoformat()
        # remove special chars from uid
        self.uid = self.uid.translate(maketrans('', ''), '-:.')
        # test cases loaded to run in this session, key is testCase.uid
        self.cases = {}
        # uid of last run test case with given name 
        self.caseUidByName = {}
        # if result of any stage i.a. init, test case stages or finalize
        # ended with non-zero status code 
        self.failed = False

    def addCaseRun(self, tc):
        '''
        Registers run of test case. Gives unique id (uid) for started
        test case, because one test case can be run many time within test
        suite session.
        @param tc: TestCase definition object
        '''
        tc.uid = tc.name + '-' + datetime.datetime.now().isoformat()
        tc.uid = tc.uid.translate(maketrans('', ''), '-:.') # remove special
                                                            # chars from uid
        tc.initDate = datetime.datetime.now()

        self.cases[tc.uid] = tc
        self.caseUidByName[tc.name] = tc.uid

    def addStageResult(self, state, result, uid=None, slave_name=None):
        '''
        Adds all information about stage that has finished to test suite session
        object. Stage are e.g.: initialize suite on some slave, run test case
        on some slave etc.
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

    def getTestCaseStages(self, test_case_uid):
        '''
        Retrieve test case stages for given test case unique id.
        @param test_case_uid:
        '''
        stages = [v for v in self.stagesResults if v[2] == test_case_uid]
        return stages
    

def extractSuiteName(path):
    '''
    Return the suite name from the given path.
    '''
    (modPath, modFile) = os.path.split(path)
    modPath = os.path.abspath(modPath)
    (modName, ext) = os.path.splitext(modFile)

    return (modName, ext, modPath, modFile)

def loadTestCasesDefs(path, tests):
    '''
    Loads TestCase definitions from .py file. Search for getTestCases function
    in the file and expects list of testCases to be returned.

    @param path: path for .py files, storing cluster definitions
    '''
    testCases = {}
    
    for test in tests:
        try:
            tc = TestCase()
            tc.name = test
            
            tcpath = path + os.sep + 'tc' + os.sep + test
            for file in os.listdir(tcpath):
                if file == 'init.sh':
                    tc.initialize = readFile(os.path.join(tcpath, file))
                elif file == 'run.sh':
                    tc.run = readFile(os.path.join(tcpath, file))
                elif file == 'finalize.sh':
                    tc.finalize = readFile(os.path.join(tcpath, file))
            
            tc.validateStatic()
            testCases[test] = tc
            
        except Exception, e:
            raise TestSuiteException('Error occurred loading test cases: %s' % e) 
                   
    if not testCases:
        raise TestSuiteException('No test cases found in test suite')

    return testCases

def loadTestSuiteDef(path):
    '''
    Load a single test suite definition.

    @param path: path to the suite definition to be loaded.
    '''
    fp = path
    (modName, ext, modPath, modFile) = extractSuiteName(fp)
    obj = None
    if os.path.isfile(fp) and ext == '.py':
        mod = None
        try:
            if not modPath in sys.path:
                sys.path.insert(0, modPath)

            method = 'getTestSuite'
            if sys.modules.has_key(modName):
                del sys.modules[modName]
            mod = __import__(modName, globals(), {}, [method])
            
            fun = getattr(mod, method)
            obj = fun()

            if obj.name != modName:
                raise TestSuiteException(('Test Suite %s in file %s ' + \
                  'does not match filename.') % (obj.name, modFile))
            obj.definitionFile = modFile
            
            # Resolve script URLs into actual text
            root_path = os.sep.join(path.split(os.sep)[:-1])
            obj.initialize = resolveScript(obj.initialize, root_path) 
            obj.finalize = resolveScript(obj.finalize, root_path)
            
            #load TestCases
            obj.testCases = loadTestCasesDefs(modPath, obj.tests)
            #after load, check if testSuite definition is correct
            obj.validateStatic()
        except TypeError, e:
            raise TestSuiteException(("TypeError in test suite definition " + \
                  "file %s: %s") % (modFile, e))
        except NameError, e:
            raise TestSuiteException(("NameError in test suite definition file " + \
                  " %s: %s") % (modFile, e))
        except AttributeError, e:
            raise TestSuiteException(("AttributeError in test suite " + \
                                      "definition file %s: %s") % (modFile, e))
        except ImportError, e:
            raise TestSuiteException("ImportError " + \
                  "during test suite %s import: %s" % (modFile, e))
        except Exception, e:
            raise TestSuiteException('Error: %s' % e.desc)
    elif ext == ".pyc":
        return None
    else:
        raise TestSuiteException(("File %s " + \
              "seems not to be a test suite definition.") % fp)
    return obj

def loadTestSuiteDefs(path):
    '''
    Loads TestSuite and TestCase definitions from .py files
    stored in path directory.

    @param path: path for .py files, storing cluster definitions
    '''
    testSuites = []
    
    if os.path.exists(path):
        for f in os.listdir(path):
            fp = path + os.sep + f + os.sep + f + '.py'
            try:
                ts = loadTestSuiteDef(fp)
                if ts:
                    ts.state = State(TestSuite.S_DEF_OK)
                    testSuites.append(ts)
            except TestSuiteException, e:
                ts = TestSuite()
                ts.name = f
                ts.state = State((-1, e.desc))
                testSuites.append(ts)
                LOGGER.error(e)

    return testSuites

def resolveScript(definition, root_path):
    '''
    Grabs a script from some arbitrary path.
    
    TODO: add more error handling
    '''
    script = ''
    # If already a bash script, nothing to do
    if definition.startswith('#!/bin/bash'):
        pass
    # Absolute file path
    elif definition.startswith('file:///'):
        with open(definition[7:], 'r') as f:
            script = f.read()
    # Relative file path
    elif definition.startswith('file://'):
        with open(root_path + os.sep + definition[7:], 'r') as f:
            script = f.read()
    # URL
    elif definition.startswith('http://'):
        script = urllib2.urlopen(definition).read()
    
    # NoneType means no script at all
    elif not definition:
        return
    else:
        raise TestSuiteException("Unknown script definition type: %s." % definition)
    
    return script

def readFile(path):
    with open(os.path.abspath(path), 'r') as f:
        return f.read()
