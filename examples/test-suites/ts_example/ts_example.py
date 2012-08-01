from XrdTest.TestUtils import TestSuite, TestCase

def getTestSuite():
    ts = TestSuite()

    ts.name = "ts_example"
    ts.clusters = ['cluster_example']
    ts.machines = ['metamanager1', 'manager1', 'manager2', 'ds1', 'ds2', 'ds3', 'ds4', 'client1']
    ts.tests = ['copy_example']
    
    ts.schedule = dict(second='39', minute='20', hour='*', day='*', month='*')

    ts.initialize = "file://suite_init.sh"
    ts.finalize = "file://suite_finalize.sh"

    return ts

def getTestCases():
    tcs = []

    tc1 = TestCase()
    tc1.name = "copy_example"
    tc1.initialize = "file://tc/" + tc1.name + "/init.sh"
    tc1.run = "file://tc/" + tc1.name + "/run.sh"
    tc1.finalize = "file://tc/" + tc1.name + "/finalize.sh"
    tcs.append(tc1)

    return tcs
