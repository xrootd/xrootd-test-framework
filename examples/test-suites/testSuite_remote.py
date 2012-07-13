from XrdTest.TestUtils import TestSuite, TestCase

def getTestSuite():
    ts = TestSuite()

    ts.name = "testSuite_remote"
    ts.clusters = ['cluster_remote']
    ts.machines = ["slave1", "slave2", "slave3"]
    ts.tests = ['BasicInstall']
    ts.schedule = dict(second='1', minute='55', hour='*', day='*', month='*')

    ts.initialize = "http://128.141.48.96:8080/showScript/ts_basic_init.sh"
    ts.finalize = "http://128.141.48.96:8080/showScript/ts_basic_finalize.sh"

    return ts

def getTestCases():
    tcs = []

    tc1 = TestCase()
    tc1.name = "BasicInstall"
    tc1.initialize = "http://128.141.48.96:8080/showScript/tc_basic_init.sh"
    tc1.run = "http://128.141.48.96:8080/showScript/tc_basic_run.sh"
    tc1.finalize = "http://128.141.48.96:8080/showScript/tc_basic_finalize.sh"
    tcs.append(tc1)

    return tcs
