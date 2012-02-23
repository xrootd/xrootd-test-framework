from TestUtils import TestSuite, TestCase

def getTestSuite():
    ts = TestSuite()

    ts.name = "testSuite_remote"
    ts.machines = ["new1.xrd.test", "new2.xrd.test"]
    ts.tests = ['TheFirst']
    ts.schedule = dict(month='2', minute='*/2')

    ts.initialize = "#!/bin/bash \ntouch /tmp/testSuite_local_init.txt"
    ts.finalize = "#!/bin/bash \ntouch /tmp/testSuite_local_final.txt"
    
    return ts

def getTestCases():
    tcs = []

    tc1 = TestCase()
    tc1.name = "TheFirst"
    tc1.machines = ["new1.xrd.test", "new2.xrd.test"]
    tc1.initialize = "#!/bin/bash \ntouch /tmp/testCase_Basic_init.txt"

    tc1.run = "#!/bin/bash \ntouch /tmp/testCase_Basic_run.txt \nls"

    tc1.finalize = "#!/bin/bash \ntouch /tmp/testCase_Basic_final.txt"
    tcs.append(tc1)


    return tcs
