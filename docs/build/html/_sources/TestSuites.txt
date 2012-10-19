*******************
Writing test suites
*******************

This page describes how to write test suites for the XrdTest Framework. For
details on how to set up a repository to hold your test suites, see 
:doc:`Configuration`.

.. note::
    Full examples can be found in the ``examples`` directory.
    
Directory Structure
===================

Test suites have a specific directory structure which must be adhered to, 
explained below:

* Each test suite resides in its own directory.
* Each test suite has a definition file, which uses Python syntax. It is loaded
  dynamically as a Python function at runtime, so it must be syntactically 
  correct. It must have a specific name (see :ref:`naming_consistency` below).
* Each test suite has a mandatory global **initialization** script, which is
  used to set up the (xrootd) environment ready for running test cases (see
  :ref:`suite_init` below).
* Test suites can optionally have a global **finalization** script, generally
  used to perform cleanup tasks, such as removing files from data servers,
  removing authentication credentials etc. (see :ref:`suite_fin` below).
* Each test suite has a subdirectory (generally called **tc**) which holds the 
  set of test cases for this suite.
  
    * Each test case resides in its own subdirectory. The name of the directory 
      defines the name of the test case.
    * Each test case has a mandatory **initialization** script
    * Each test case has a mandatory **run** script.
    * Test cases can optionally have a **finalization** script.

.. _naming_consistency:

Naming Consistency
------------------

You are generally free to choose your own naming conventions, but there are some
consistency rules that must be followed, explained in this section.

The test suite name is arbitrary, but in the CERN ``xrootd-testsuite`` 
repository we have a naming convention of ``ts_<numerical id>_<shorthand 
description>``. For example, the suite which tests GSI functionality is named
**ts_006_gsi**.

The test suite definition file must be in the root directory of the test suite
folder, and it must have the same name as the folder, with a ``.py`` extension.

Additionally, the **ts.name** attribute in the definition file must also share
the name of the folder/file.

.. _suite_init:

The @tag@ system
================

@slavename@, @diskmounts@, @port@, @proto@

Extension?

Available functions (API-like)
==============================

log(), stamp(), assert_fail()

stdout and stderr
=================

Writing global suite initialization scripts
===========================================

.. _suite_fin:

Writing global suite finalization scripts
=========================================
