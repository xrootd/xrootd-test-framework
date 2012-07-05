from XrdTest.TestUtils import TestSuite, TestCase

def getTestSuite():
    ts = TestSuite()

    ts.name = "testSuite_remote"
    ts.clusters = ['cluster_remote']
    ts.machines = ["new1"]
    ts.tests = ['BasicInstall']
    ts.schedule = dict(month='3')

    ts.initialize = "http://master.xrd.test:8080/showScript/sinit_remote.sh"
    ts.finalize = """
    #!/bin/bash
    touch /tmp/testSuite_remote_finalize.txt"""

    return ts

def getTestCases():
    tcs = []

    tc1 = TestCase()
    tc1.name = "BasicInstall"
    tc1.initialize = "#!/bin/bash \ntouch /tmp/testCase_Basic_init.txt"
    tc1.run = "#!/bin/bash \ntouch /tmp/testCase_Basic_run.txt \nls"
    tc1.finalize = "#!/bin/bash \ntouch /tmp/testCase_Basic_final.txt"
    tcs.append(tc1)

    return tcs
