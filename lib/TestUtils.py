#!/usr/bin/env python
#-------------------------------------------------------------------------------
# Author: Lukasz Trzaska <lukasz.trzaska@cern.ch>
# Date:   22.08.2011
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
logging.basicConfig(format='%(levelname)s line %(lineno)d: %(message)s', \
                    level=logging.INFO)
LOGGER = logging.getLogger(__name__)
LOGGER.debug("Running script: " + __file__)
#------------------------------------------------------------------------------ 
class TestSuite:
    schedule = ""   # define when the test should be run (cron style)
    clusters = []   # a list of virtual clusters needed by the test to be spawned
                    # on a hypervisor
    machines = []   # names of machines, including the virtual machines that
                    # are needed by the test
    initialize = "" # an URL to a shell script (starts with http://) or a shell
                    # script (starts with #!) that defines the commands that need
                    # to be run on each test slave before any test case can run
                    # if it fails then the entire test suit should be considered as
                    # failed
    finalize = ""   # an URL to shell script or a shell script that defines the
                    # clean up procedures to be run after all the tests cases
                    # are completed
    tests = []      # a list of test cases as defined below
#-------------------------------------------------------------------------------
    def validateStatic(self):
        '''
        Method checks if definition is statically correct.
        '''
        #@todo: 
        return True

#------------------------------------------------------------------------------ 
class TestCase:
    name = ""       # name of the test case
    machines = []   # names of the machines that the test case should run on
    initialize = "" # a shell script or a link to a shell script that should
                    # be run on each machine. The initialize script should
                    # be completed on each machine before the run script can run.
                    # initialization failure is considerd as a test case failure
    run = ""        # a shell script that is the actual test, if the script fails
                    # then the test case is considered as failed, the run scripts
                    # have to finish running on all the mashines before the finalize
                    # script can be invoked
    finalize = ""  # a script defining the finalization procedures
    #---------------------------------------------------------------------------
    def validateStatic(self):
        '''
        Method checks if definition is statically correct.
        '''
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
class TestSuiteException(Exception):
    '''
    General Exception raised by module
    '''
    ERR_UNKNOWN = 1
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
def loadTestSuitsDefs(path):
    '''
    Loads TestSuits definitions from .py files stored in path directory
    @param path: path for .py files, storing cluster definitions
    '''
    global LOGGER

    testSuits = []
    if os.path.exists(path):
        for f in os.listdir(path):
            fp = path + os.sep + f
            (modPath, modFile) = os.path.split(fp)
            modPath = os.path.abspath(modPath)
            (modName, ext) = os.path.splitext(modFile)

            if os.path.isfile(fp) and ext == '.py':
                mod = None
                cl = None
                try:
                    if not modPath in sys.path:
                        sys.path.insert(0, modPath)

                    method = 'getTestSuite'
                    mod = __import__(modName, {}, {}, [method])
                    obj = getattr(mod, method)
                    obj.definitionFile = modFile
                    #after load, check if cluster definition is correct
                    obj.validateStatic()
                    testSuits.append(obj)
                except AttributeError, e:
                    LOGGER.exception(e)
                    raise TestSuiteException("Method " + method + \
                          "can't be found in " + \
                          "file: " + str(modFile))
                except ImportError, e:
                    LOGGER.exception(e)
    return testSuits
#------------------------------------------------------------------------------- 
def loadTestCasesDefs(path):
    '''
    Loads TestCases definitions from .py files stored in path directory
    @param path: path for .py files, storing cluster definitions
    '''
    global LOGGER

    testCases = []
    if os.path.exists(path):
        for f in os.listdir(path):
            fp = path + os.sep + f
            (modPath, modFile) = os.path.split(fp)
            modPath = os.path.abspath(modPath)
            (modName, ext) = os.path.splitext(modFile)

            if os.path.isfile(fp) and ext == '.py':
                mod = None
                cl = None
                try:
                    if not modPath in sys.path:
                        sys.path.insert(0, modPath)

                    method = 'getTestCase'
                    mod = __import__(modName, {}, {}, [method])
                    obj = getattr(mod, method)
                    obj.definitionFile = modFile
                    #after load, check if cluster definition is correct
                    obj.validateStatic()
                    testCases.append(obj)
                except AttributeError, e:
                    LOGGER.exception(e)
                    raise TestSuiteException("Method " + method + \
                          "can't be found in " + \
                          "file: " + str(modFile))
                except ImportError:
                    LOGGER.exception(e)
    return testCases
