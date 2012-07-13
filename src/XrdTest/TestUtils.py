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
# File:   TestManager module
# Desc:   Virtual machines network manager
#-------------------------------------------------------------------------------
# Imports
#---------------------------------------------------------------------------
import logging
import os
import sys
#-------------------------------------------------------------------------------
# Global variables
#-------------------------------------------------------------------------------
logging.basicConfig(format='%(asctime)s %(levelname)s ' + \
                    '[%(filename)s %(lineno)d] ' + \
                    '%(message)s', level=logging.INFO)
LOGGER = logging.getLogger(__name__)
LOGGER.debug("Running script: " + __file__)
#-------------------------------------------------------------------------------
class TestSuiteException(Exception):
    '''
    General Exception raised by module
    '''
    ERR_UNKNOWN     = 1
    ERR_CRITICAL    = 2
    #---------------------------------------------------------------------------
    def __init__(self, desc, typeFlag=ERR_UNKNOWN):
        '''
        Constructs Exception
        @param desc: description of an error
        @param typeFlag: represents type of an error, taken from class constants
        '''
        self.desc = desc
        self.type = typeFlag
    #---------------------------------------------------------------------------
    def __str__(self):
        '''
        Returns textual representation of an error
        '''
        return repr(self.desc)
#------------------------------------------------------------------------------ 
class TestSuite:

    #---------------------------------------------------------------------------
    def __init__(self):
        #-----------------------------------------------------------------------
        # Defining attributes
        self.name = ""      # name of test suite, has to the same as
                            # the name of test suite definition file
        self.descName = ""  # name of test suite readable for human, only
                            # for informational need
        self.schedule = {}  # define when the test should be run (cron style)
                            # reference: APScheduler cronschedule
        self.clusters = []  # a list of virtual clusters needed by 
                            # the test to be spawned on a hypervisor
        self.machines = []  # names of machines, including the virtual machines 
                            # that are needed by the test
        self.initialize = "" 
                            # an URL to a shell script (starts with http://) or 
                            # a shell script (starts with #!) that defines 
                            # the commands that need to be run on each test slave 
                            # before any test case can run if it fails then the 
                            # entire test suit should be considered as failed
        self.finalize = ""  # an URL to shell script or a shell script that 
                            # defines the clean up procedures to be run after 
                            # all the tests cases are completed
        self.tests = []     # a list of test cases names as defined below

        #-----------------------------------------------------------------------
        # Fields beneath are filled automatically by system
        self.defComplete = True # means that all cluster definitions that the
                                # cluster depends on are available
        self.jobFun = None      # handle to function that will be used
                                # by scheduler. Has to be kept in case of
                                # unscheduling.
        self.machinesAutoFilled = False #if machines were empty, system has
                                # to remember to reload them every time cluster
                                # definition changes
        self.testCases  = []    # filled automatically by load test suite defs.
                                # holds Python objectsrepresenting test cases
    #---------------------------------------------------------------------------
    def validateStatic(self):
        '''
        Method checks if definition (e.g given names) is statically correct.
        '''
        #@todo: finish it
        if not self.name or " " in self.name:
            raise TestSuiteException(("No name given in TestSuite " + \
                                      "definition or the name %s have " + \
                                      "is not alphanumeric without spaces.") % \
                                      self.name, \
                                      TestSuiteException.ERR_CRITICAL)
        if not self.schedule:
            raise TestSuiteException(("No scheduler expression " + \
                                      "given in TestSuite %s definition.") % \
                                      self.name, \
                                      TestSuiteException.ERR_CRITICAL)
        if not self.initialize or not self.finalize:
            raise TestSuiteException(("No initialize or finalize script " + \
                                      "in TestSuite %s definition") % \
                                      self.name, \
                                      TestSuiteException.ERR_CRITICAL)
        if not len(self.tests):
            raise TestSuiteException(("No test cases or no machines " + \
                                      "given in TestSuite %s definition.") % \
                                      self.name, \
                                      TestSuiteException.ERR_CRITICAL)
        for t in self.tests:
            if not self.testCases.has_key(t):
                raise TestSuiteException(("No TestCase %s defined but used" + \
                                         " in TestSuite definition") % str(t), \
                                          TestSuiteException.ERR_CRITICAL)
        return True
    #---------------------------------------------------------------------------
    def checkIfDefComplete(self, clusters):
        if self.machinesAutoFilled:
            self.machines = []

        for cluN in self.clusters:
            if not cluN in clusters:
                self.defEnabled = False
                raise TestSuiteException(\
                ("Cluster %s in suite %s definition " + \
                "doesn't exist in clusters' definitions.") % (cluN, self.name))
        #-----------------------------------------------------------------------
        # check if all required machines are connected and idle
        if not len(self.machines):
            self.machinesAutoFilled = True
            for cName in self.clusters:
                self.machines.extend(\
                [h.name for h in clusters[cName].hosts])
                LOGGER.info(("Host list for suite %s " + \
                            "filled automatically with %s") % \
                            (self.name, self.machines))

    #---------------------------------------------------------------------------
    # Constants
    S_IDLE                   = (10, "idle")

    S_WAIT_4_INIT            = (20, "wait for suite initialization")
    S_SLAVE_INITIALIZED      = (21, "slave initialized")
    S_ALL_INITIALIZED        = (22, "all machines initialized")

    S_WAIT_4_FINALIZE        = (30, "wait for suite finalization")
    S_SLAVE_FINALIZED        = (31, "slave finalized")
    S_ALL_FINALIZED          = (32, "all machines initialized")

    S_WAIT_4_TEST_INIT       = (40, "sent test init")
    S_SLAVE_TEST_INITIALIZED = (41, "test initialized on a slave")
    S_ALL_TEST_INITIALIZED   = (42, "test initialized on all slaves")

    S_WAIT_4_TEST_RUN        = (43, "sent test to run")
    S_SLAVE_TEST_RUN_FINISHED= (44, "test run finished on a slave")
    S_ALL_TEST_RUN_FINISHED  = (45, "test run finished on all slaves")

    S_WAIT_4_TEST_FINALIZE   = (46, "send test to finalize")
    S_SLAVE_TEST_FINALIZED   = (47, "test finalized on a slave")
    S_ALL_TEST_FINALIZED     = (48, "test finalized on all slaves")

    S_INIT_ERROR             = (-22, "initialization error")
#------------------------------------------------------------------------------ 
class TestCase:
    def __init__(self):
        self.name = ""      # name of the test case
        self.machines = []  # names of the machines that the test case 
                            # should run on. If empty: it runs on all
                            # machines in test suite
        self.initialize = ""# a shell script or a link to a shell script
                            # that should be run on each machine. The 
                            # initialize script should be completed on
                            # each machine before the run script can run.
                            # initialization failure is considerd as a 
                            # test case failure
        self.run = ""       # a shell script that is the actual test, if
                            # the script fails then the test case is 
                            # considered as failed, the run scripts
                            # have to finish running on all the mashines
                            # before the finalize script can be invoked
        self.finalize = ""  # a script defining the finalization procedures
        #-----------------------------------------------------------------------
        # Fields beneath are filled automatically by system
        self.resultsFromMachines = {}   # keeps results of all test stages
                                        # on those machines. Index is a machine
        self.uid = ""
        self.initDate = None        #filled with datetime.datetime.now()
    #---------------------------------------------------------------------------
    def validateStatic(self):
        '''
        Method checks if definition (e.g given names) is statically correct.
        '''
        if not self.name or " " in self.name:
            raise TestSuiteException(("No name given in TestCase " + \
                                      "definition or the name %s have " + \
                                      "is not alphanumeric without spaces.") % \
                                     self.name, \
                                      TestSuiteException.ERR_CRITICAL)
        return True

#In all the scripts mentioned above the string @slavename@ should be replaced
#with the actual machine name, so that the following statements are possible
#int he scripts:
#
#if [ @slavename@ == machine1 ]; then
#  foo
#elif [ @slavename@ == machine2 ]; then
#  bar
#else
#  foobar
#fi
#-------------------------------------------------------------------------------
def extractSuiteName(path):
    (modPath, modFile) = os.path.split(path)
    modPath = os.path.abspath(modPath)
    (modName, ext) = os.path.splitext(modFile)

    return (modName, ext, modPath, modFile)
#------------------------------------------------------------------------------- 
def loadTestCasesDefs(filePath):
    '''
    Loads TestCases definitions from .py file. Search for getTestCases function
    in the file and expects list of testCases to be returned.
    @param path: path for .py files, storing cluster definitions
    '''
    global LOGGER

    testCases = {}

    (modName, ext, modPath, modFile) = extractSuiteName(filePath)

    if os.path.isfile(filePath) and ext == '.py':
        mod = None
        try:
            if not modPath in sys.path:
                sys.path.insert(0, modPath)

            method = 'getTestCases'
            if sys.modules.has_key(modName):
                del sys.modules[modName]
            mod = __import__(modName, {}, {}, [method])
            fun = getattr(mod, method)
            objs = fun()

            if objs and getattr(objs, '__iter__', False):
                for obj in objs:
                    obj.definitionFile = modFile
                    #after load, check if cluster definition is correct
                    obj.validateStatic()
                testCases[obj.name] = obj
            else:
                raise TestSuiteException("Method " + method + \
                  " doesn't return list of objects in " + \
                  " file: " + str(modFile))
        except TypeError, e:
            raise TestSuiteException(("TypeError while loading test case " + \
                          "definition file %s: %s") % (modFile, e))
        except AttributeError, e:
            raise TestSuiteException(("AttributeError during loading test" + \
                          "case definition file %s: %s") % (modFile, e))
        except ImportError:
            raise TestSuiteException(("ImportError during loading test case"+ \
                          "definition file %s: %s") % (modFile, e))
        except Exception, e:
            raise TestSuiteException(("Exception during loading test case"+ \
                          "definition file %s: %s") % (modFile, e))
    return testCases

#-------------------------------------------------------------------------------
def loadTestSuiteDef(path):
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
                raise TestSuiteException(("TestSuite name %s in file %s" + \
                  " is not the same as filename <test_suite_name>.py") % \
                                         (obj.name, modFile))
            obj.definitionFile = modFile
            #load TestCases
            obj.testCases = loadTestCasesDefs(fp)
            #after load, check if testSuite definition is correct
            obj.validateStatic()
        except TypeError, e:
            raise TestSuiteException(("TypeError in test suite definition " + \
                  "file %s: %s") % (modFile, e))
        except NameError, e:
            raise TestSuiteException(("Name error in test suite def file " + \
                  " %s: %s") % (modFile, e))
        except AttributeError, e:
            raise TestSuiteException(("Sth can't be found in test suite " + \
                                      "definition file %s: %s") % (modFile, e))
        except ImportError, e:
            raise TestSuiteException("Import error " + \
                  "during test suite %s import: %s" % (modFile, e))
        except Exception, e:
            raise TestSuiteException("Exception occured " + \
                  "during test suite %s import: %s" % (modFile, e))
    elif ext == ".pyc":
        return None
    else:
        raise TestSuiteException(("File %s " + \
              "seems not to be test suite definition.") % fp)
    return obj
#------------------------------------------------------------------------------ 
def loadTestSuitsDefs(path):
    '''
    Loads TestSuits and TestCases definitions from .py files 
    stored in path directory.
    @param path: path for .py files, storing cluster definitions
    '''
    global LOGGER

    testSuits = {}
    if os.path.exists(path):
        for f in os.listdir(path):
            fp = path + os.sep + f
            try:
                ts = loadTestSuiteDef(fp)
                if ts:
                    testSuits[ts.name] = ts
            except TestSuiteException, e:
                raise e

    return testSuits
