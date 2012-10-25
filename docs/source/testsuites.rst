*******************
Writing test suites
*******************

This page describes how to write test suites for the XrdTest Framework. For
details on how to set up a repository to hold your test suites, see 
:doc:`config-master`.

.. note::
    Full examples can be found in the ``examples`` directory.
    
    
Structure of a test suite
=========================

Test suites have a specific structure which must be adhered to, 
explained below:

* Each test suite resides in its own directory.
* Each test suite has a definition file, which uses Python syntax. It is loaded
  dynamically as a Python function at runtime, so it must be syntactically 
  correct. It must have a specific name (see :ref:`def_file` below).
* Each test suite has a mandatory global **initialization** script, which is
  used to set up the (xrootd) environment ready for running test cases (see
  :ref:`scripts` below).
* Test suites can optionally have a global **finalization** script, generally
  used to perform cleanup tasks, such as removing files from data servers,
  removing authentication credentials etc. (see :ref:`scripts` below).
* Each test suite has a subdirectory called **tc** which holds the set of 
  test cases for this suite.
  
    * Each test case resides in its own subdirectory. The name of the directory 
      defines the name of the test case.
    * Each test case has a mandatory **initialization** script
    * Each test case has a mandatory **run** script.
    * Test cases can optionally have a **finalization** script.
   
   
.. _def_file:   
 
The definition file
-------------------

The test suite definition file must be in the root directory of the test suite
directory, and it must have the same name as the folder, with a ``.py`` extension.

A test suite is defined inside a function named ``getTestSuite()`` which takes 
no parameters. Here is an example of the beginning of a definition file::

  from XrdTest.TestUtils import TestSuite

  def getTestSuite():
      
      ts = TestSuite()
      ts.name = "ts_002_frm"
      
The ``ts.name`` attribute is the unique name of the test suite. It must match 
the name of the file exactly (minus the *.py* extension) and also match the 
directory name in which this test suite resides.

The test suite name is arbitrary, but in the CERN ``xrootd-testsuite`` 
repository we have a naming convention of ``ts_<numerical id>_<shorthand 
description>``. For example, the suite which tests GSI functionality is named
**ts_006_gsi**. You are of course free to choose your own naming conventions, 
however.

Defining required clusters
^^^^^^^^^^^^^^^^^^^^^^^^^^

To define the cluster(s) which this test suite requires, include a line like 
this::

  ts.clusters = ['cluster_002_frm']			

This line is mandatory. Currently, there is only support for one cluster per
test suite. It is planned to have the ability to run multiple clusters on 
multiple hypervisors in the future. For information on how to define a cluster,
see :doc:`clusters`.

There is also the ability to specify a subset of the machines in a cluster,
with a line like this::

  ts.machines = ['frm1', 'frm2', 'ds1', 'ds2', 'client1']
  
There haven't been any use cases where this has been needed yet, but the
functionality exists if one comes along. This line is not mandatory.

Scheduling test suites
^^^^^^^^^^^^^^^^^^^^^^

To schedule the test suite to be run at particular intervals (cron-style), you
must include a line like this::

  ts.schedule = dict(second='30', minute='08', hour='*', day='*', month='1')
  
This line is mandatory.

Defining what is run
^^^^^^^^^^^^^^^^^^^^

To define which test cases will be run in this suite, include a line similar
to this::
    
  ts.tests = ['copy_to', 'copy_from']
  
This line is mandatory. If a test case exists in the **tc** directory, but is
not included in the line in the definition file, it will not be run.

To point to the suite initialization script, include a line like this::
    
  ts.initialize = "file://suite_init.sh"
  
This line can be a relative file URL (as above), an absolute file URL, or a 
HTTP URL. The initialization script is mandatory.
  
To point to the suite finalization script, include a line like this::

  ts.finalize = "file://suite_finalize.sh"

The finalization script is not mandatory. It can be used for general cleaning
up after all test cases have been run.

Including log files
^^^^^^^^^^^^^^^^^^^

The framework has functionality for retrieving arbitrary log files from each
slave at each stage of the test suite. To use this feature, include a line
like this::
    
  ts.logs = ['/var/log/xrootd/@slavename@/xrootd.log',
             '/var/log/xrootd/@slavename@/cmsd.log',
             '/var/log/XrdTest/XrdTestSlave.log']

You should provide the path to any log files which will be useful to inspect.
It is possible to use the @slavename@ tag in the log file path (See 
:ref:`tagging` for an explanation of the @slavename@ and other tags). It can 
be useful to include the slave log (XrdTestSlave.log) for debugging purposes.

Getting email alerts
^^^^^^^^^^^^^^^^^^^^

It is possible to give an arbitrary list of email addresses, each of which can
be notified of the outcome of a test suite run, to a specified level of verbosity.

The list of email addresses is defined with a line like the following::
    
  ts.alert_emails = ['jsalmon@cern.ch', 'foo@bar.com']

The amount of email alerts to be sent is configured with policy lines like the
following::
    
  ts.alert_success = 'SUITE'
  ts.alert_failure = 'CASE'

There is a separate policy for failure notifications and success notifications
for flexibility. The possible options for both policies are:

* ``SUITE`` - Send an email about the final state of the entire test suite
  (success or failure).
* ``CASE`` - Send an email about the final state of each individual test case
  (success or failure). Implied SUITE.
* ``NONE`` - Don't send any emails.

The default options are generally OK, i.e. ``CASE`` for failure alerts (as you 
want to know if the test suite failed and also which individual test cases failed)
and ``SUITE`` for success alerts (you don't care if each test case succeeds, only
that the whole suite succeeds). You might want to put ``NONE`` for the success 
policy if you really only care about failures.

.. _scripts:

Writing initialization/run/finalization scripts
===============================================

As mentioned earlier, each test suite has a mandatory global initialization 
script, an optional global finalization script, and a set if initialization/
run/finalization scripts for each test case.

The framework has been designed in this way, so that actions can be synchronized
between participants (slaves) in the cluster. For example, if a slave completes
its global initialization script, it will wait for all other slaves to complete
theirs before moving on to the next stage. Similarly, a slave will not begin the
run stage of a test case until it and all other slaves have completed the test
case initialization stage. The XrdTest Master is actually responsible for
orchestrating this activity.

**It is important to note that** should the global initialization script fail
on any slave for any reason, then the **entire test suite** will be considered
as failed, and no test cases will be run. A command that returns a non-zero
exit code is considered as a failure, unless specifically stated otherwise by
using the ``assert_fail`` function (see :ref:`functions` below).

If a **test case** initialization script fails, the suite will continue to run.
The same is true for the remaining stages of the suite.

Also note that you do not need to worry about *stdout* and *stderr*. Anything 
that is printed to *stderr* will be redirected to *stdout*. This is due to
both ease of use, and to problems with Python's ``subprocess`` module and the
way it handles *stderr*.

The framework provides some features to make the scripts more flexible,explained 
below.

.. _tagging:

The ``@tag@`` system
--------------------

There are some special keywords which can be used inside any test suite script.
These keywords, or *tags*, have a descriptive name enclosed with ``@`` symbols.
Each tag within a script will be replaced with an appropriate real value at 
runtime, based upon which slave is currently running the script, the cluster
configuration, and the parameters with which the master is to be contacted.

The currently available tags are as follows:

* ``@slavename@`` - The FQDN of the current slave running the script. This allows
  one to write a single script containing if/else blocks to determine which piece
  of code the current slave will run, based upon its name. 
* ``@port@`` - The port on which the master should be contacted (defined in the
  master configuration file, see :doc:`config-master`).
* ``@proto@`` - The protocol by which the master should be contacted (defined in
  the master configuration file, see :doc:`config-master`).
* ``@diskmounts@`` - Gets resolved to the appropriate disk mount command(s) for 
  the current slave. Disks are always mounted as ``ext4`` using ``user_xattr``.

It is planned to allow user extensions to the tagging system sometime in the 
future, so that arbitrary tags can be used inside scripts for even greater
flexibility.

.. _functions:

Available functions
-------------------

There is a small library of functions (located in */etc/XrdTest/utils*) that can
be used by default in test scripts. To use these functions, simply source the 
file inside the script like this::

    #!/bin/bash
    source /etc/XrdTest/utils/functions.sh

A brief description of the currently available functions:

* ``assert_fail`` - a function to assert the non-zero exit code of a function.
  Used for testing invalid use cases and verifiying that they fail as they should.
  For example::
    
    assert_fail rm non_existent
  
  will return zero and not cause the script to exit (as would have happened if
  the ``assert_fail`` command were not used).
    
* ``log`` - Used for timestamping and printing single-line commands or progress
  messages. For example::
    
    log "Initializing test suite on slave @slavename@"
  
  will print a timestamped line in the session log which looks like this::
    
    [10:49:20] Initializing test suite on slave manager1.xrd.test
    
* ``stamp`` - Used for timestamping and printing entire command outputs. For
  example::
    
    stamp ls -al /data
  
  will produce output like this::
    
    [09:57:37]  total 51208
    [09:57:37]  drwxr-xr-x.  2 daemon daemon     4096 Oct 22 09:57 .
    [09:57:37]  dr-xr-xr-x. 25 root   root       4096 Oct 22 09:52 ..
    [09:57:37]  -rw-r--r--.  1 root   root   52428800 Oct 22 09:57 some_file

