from TestUtils import TestSuite, TestCase

def getTestSuite():
    ts = TestSuite()

    ts.name = "testSuite_remote"
    ts.machines = ["luk-laptop", "lxbrl2705.cern.ch"]
    ts.tests = ['First-123']
    ts.schedule = dict(month='2', minute='*/2')

    ts.initialize = "#!/bin/bash \ntouch /tmp/testSuite_local_init.txt"
    ts.finalize = "#!/bin/bash \ntouch /tmp/testSuite_local_final.txt"
    
    return ts

def getTestCases():
    tcs = []

    tc1 = TestCase()
    tc1.name = "First-123"
    tc1.machines = ["lxbrl2705.cern.ch"]
    tc1.initialize = "#!/bin/bash \ntouch /tmp/testCase_Basic_init.txt"

    tc1.run = "#!/bin/bash \ntouch /tmp/testCase_Basic_run.txt \nls"
    
    tc1.finalize = "#!/bin/bash \ntouch /tmp/testCase_Basic_final.txt"
    tcs.append(tc1)


    return tcs
