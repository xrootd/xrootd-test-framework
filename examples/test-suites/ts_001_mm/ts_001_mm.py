from XrdTest.TestUtils import TestSuite, TestCase

def getTestSuite():
    ts = TestSuite()

    # Unique name for this test suite. Currently, it must match the filename
    # exactly, minus the extension. (mandatory)
    ts.name = "ts_001_mm"
    # Names of all clusters which this test suite requires. (mandatory)
    ts.clusters = ['cluster_001_mm']
    # Names of all machines required by this test suite (optional)
    ts.machines = ['metamanager1', 'manager1', 'manager2', 'ds1', 'ds2', 'ds3', 'ds4', 'client1']
    # Names of test cases to be run in this suite. These are actually the names
    # of the subfolders in the tc/ directory. Each test case subdirectory must
    # contain at least an initialization script called init.sh and a run script
    # called run.sh. Also an optional finalization script called finalize.sh can
    # be included. (mandatory)
    ts.tests = ['simple_copy_to', 'simple_copy_from']
    # Cron-style scheduler expression for this suite. (mandatory)
    ts.schedule = dict(second='00', minute='09', hour='*', day='*', month='1')
    # Path to the test suite initialization script. Usually in the same directory
    # as this definition, and usually called suite_init.sh. Can also optionally
    # be an HTTP URL, an absolute file path, or an inline script. (mandatory)
    ts.initialize = "file://suite_init.sh"
    # Path to the test suite finalization script. (optional)
    ts.finalize = "file://suite_finalize.sh"

    return ts
