from TestUtils import TestSuite, TestCase

def getTestSuite():
    ts = TestSuite()
    ts.name = "testSuite1"
    ts.machines = ["lt_puppetmaster", "lt_m1", "lt_m2", "luk-laptop"]
    ts.tests = ['First']

    return ts

def getTestCases():
    tcs = []
    tc1 = TestCase()
    tc1.name = "First"

    tcs.append(tc1)

    return tcs
