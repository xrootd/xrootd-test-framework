<<<<<<< HEAD:testSuits/testSuite_local.py
from lib.TestUtils import TestSuite, TestCase
=======
from XrdTest.TestUtils import TestSuite, TestCase
>>>>>>> unstable:examples/test-suites/testSuite_local.py

def getTestSuite():
    ts = TestSuite()

    ts.name = "testSuite_local"

    ts.schedule = dict(hour='1')

    ts.machines = ["luk-laptop"]
    ts.tests = ['Basic']

    ts.initialize = " http://localhost:8080/showScript/sinit_local.sh "
    ts.finalize = """
    #!/bin/bash 
    touch /tmp/testSuite_final.txt"""

    return ts

def getTestCases():
    tcs = []
    tc1 = TestCase()

    tc1.name = "Basic"
    tc1.machines = ["luk-laptop"]
    tc1.initialize = """
    #!/bin/bash 
    touch /tmp/testCase_Basic_init.txt"""

    tc1.run = """
    #!/bin/bash
    touch /tmp/testCase_Basic_run.txt
    """

    tc1.finalize = """
    #!/bin/bash
    touch /tmp/testCase_Basic_final.txt
    """
    tcs.append(tc1)

    return tcs
