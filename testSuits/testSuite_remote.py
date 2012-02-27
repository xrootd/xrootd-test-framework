from TestUtils import TestSuite, TestCase

def getTestSuite():
    ts = TestSuite()

    ts.name = "testSuite_remote"
    ts.clusters = ['cluster1']
    ts.machines = ["new1.xrd.test"]
    ts.tests = ['BasicInstall']
    ts.schedule = dict(month='2', second="0")
    #minute='*/1', 
    ts.initialize = "http://master.xrd.test:8080/showScript/suite_init"
    ts.finalize = "http://master.xrd.test:8080/showScript/suite_finalize"

    return ts

def getTestCases():
    tcs = []

    tc1 = TestCase()
    tc1.name = "BasicInstall"
    tc1.machines = ["new1.xrd.test"]
    tc1.initialize = "#!/bin/bash \ntouch /tmp/testCase_Basic_init.txt"

    tc1.run = "#!/bin/bash \ntouch /tmp/testCase_Basic_run.txt \nls"

    tc1.finalize = "#!/bin/bash \ntouch /tmp/testCase_Basic_final.txt"
    tcs.append(tc1)

    return tcs
