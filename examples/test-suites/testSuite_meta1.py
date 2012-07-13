<<<<<<< HEAD:testSuits/testSuite_meta1.py
from lib.TestUtils import TestSuite, TestCase
=======
from XrdTest.TestUtils import TestSuite, TestCase
>>>>>>> unstable:examples/test-suites/testSuite_meta1.py

def getTestSuite():
    ts = TestSuite()

    ts.name = "testSuite_meta1"
    ts.clusters = ['cluster_meta1']

    ts.tests = ['CorrectCopy']
    ts.schedule = dict(hour='*/30')

    ts.initialize = "http://128.141.48.96:8080/showScript/sinit_meta1.sh"
    ts.finalize = "http://128.141.48.96:8080/showScript/sfinalize_meta1.sh"

    return ts

def getTestCases():
    tcs = []

    tc1 = TestCase()
    tc1.name = "CorrectCopy"
    tc1.initialize = "http://128.141.48.96:8080/showScript/tinit_meta1.sh"
    tc1.run = """http://128.141.48.96:8080/showScript/trun_meta1.sh"""
    tc1.finalize = """#!/bin/bash
    echo "TEST FINALIZATION"
    """

#    tc2 = TestCase()
#    tc2.name = "FailingCopy"
#    tc2.initialize = "http://master.xrd.test:8080/showScript/tinit_meta1.sh"
#    tc2.run = """http://master.xrd.test:8080/showScript/trun_meta1_fail.sh"""
#    tc2.finalize = """#!/bin/bash
#    echo "TEST FINALIZATION"
#    """

    tcs.append(tc1)

    return tcs

