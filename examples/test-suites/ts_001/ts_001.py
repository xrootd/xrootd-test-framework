from XrdTest.TestUtils import TestSuite, TestCase

def getTestSuite():
    ts = TestSuite()

    ts.name = "ts_001"
    ts.clusters = ['cluster_001']
    ts.machines = ["slave1", "slave2", "slave3"]
    ts.tests = ['basic']
    ts.schedule = dict(second='50', minute='05', hour='*', day='*', month='*')

    ts.initialize = "file://tc/ts_basic_init.sh"
    ts.finalize = "file://tc/ts_basic_finalize.sh"

    return ts

def getTestCases():
    tcs = []

    tc1 = TestCase()
    tc1.name = "basic"
    tc1.initialize = "file://tc/tc_basic_init.sh"
    tc1.run = "file://tc/tc_basic_run.sh"
    tc1.finalize = "file://tc/tc_basic_finalize.sh"
    tcs.append(tc1)

    return tcs
