from TestUtils import TestSuite, TestCase

def getTestSuite():
    ts = TestSuite()
    ts.name = "local"
    ts.machines = ["luk-laptop", "lxbrl2705.cern.ch"]
    ts.tests = ['Basic']

    ts.clusters = "optionally"

    ts.initialize = "#!/bin/bash \ntouch /tmp/testSuite_local_init.txt"
    ts.finalize = "#!/bin/bash \ntouch /tmp/testSuite_local_final.txt"

    return ts

def getTestCases():
    tcs = []
    tc1 = TestCase()
    
    tc1.name = "Basic"
    tc1.machines = ["luk-laptop", "lxbrl2705.cern.ch"]
    tc1.initialize = "#!/bin/bash \ntouch /tmp/testCase_Basic_init.txt"
    
    tc1.run = "#!/bin/bash \ntouch /tmp/testCase_Basic_run.txt"
    
    tc1.finalize = "#!/bin/bash \ntouch /tmp/testCase_Basic_final.txt"
    tcs.append(tc1)

    return tcs
