********************
Master configuration
********************

This section describes how to configure the XrdTest Master framework component,
including how to set up a repository to hold test suite and cluster definitions,
web interface options, logging options and security configurations.

.. note::
    The default location for configuration files is 
    ``/etc/XrdTest/<CONFIG_FILE_NAME>.conf``.
    
The master configuration file uses the *ini*-style format of the python
``ConfigParser`` module. There are multiple sections, each of which is explained
separately below. First, the configuration directive will be given, followed by
an explanation.

Configuration sections
----------------------

``[general]``
=============
::
    
    test-repos=remote,local
    
A list of repositories to use, each of which must have a corresponding
[test-repo-<reponame>] section below. As an example, we use two test suites: one
local (``test-repo-local``), and one in a remote ``git`` repository 
(``test-repo-remote``).
::
    
    suite_sessions_file=/var/log/XrdTest/suite_history.bin
    
The path to the file which stores previous test suite history.

``[test-repo-remote]``
======================

The section for the first of our two example repositories. This repository is a
remote ``git`` repository. Currently, the framework supports localfs and ``git``
repositories only. It is planned to include ``svn`` support in the future.

.. note::
    You need passwordless access to the repository for this 
    to work (such as key-based SSH, Kerberos, or a HTTP URL). Password based 
    authentication will not work, as synchronization of the remote repository
    happens automatically at certain time intervals.

.. code-block:: python

    # Example settings for a remote git repository.
    type=git
    
    # Path to the remote repository. Accepts any valid Git URL.
    remote_repo=jsalmon@xrootd.cern.ch:/var/repos/xrootd-testsuite.git
    
    # Which local/remote branches to use.
    remote_branch=origin/master
    local_branch=master
    
    # Path where the remote repo will be checked out locally.
    local_path=/var/tmp/xrootd-testsuite
    
    # Paths to the local checkouts of cluster and test suite definitions.
    cluster_defs_path=clusters
    suite_defs_path=test-suites
    
Each directive should be fairly self-explanatory. The ``remote_repo`` directive
**accepts any valid git URL**.

It is necessary to provide a
path where the remote repository will be checked out, as the system in fact
clones the remote repository to this local path, does ``fetch``/``diff`` 
periodically, then does ``pull`` if there are changes in the remote repo.

It is also necessary to point to the directories which hold cluster and test 
suite definitions **inside the local checkout directory**. This is in case you
want to change the naming conventions to better suit your environment.

``[test-repo-local]``
=====================

The section for the second example repository. This repository is located in the
local filesystem, and is much simpler to configure than a remote one.

.. code-block:: python

    # Example settings for a local repository of cluster/test suite definitions.
    type=localfs
    
    local_path=/var/repos/xrootd-testsuite
    cluster_defs_path=clusters
    suite_defs_path=test-suites
    
You need to point to the top directory, and the subdirectories which hold cluster
and test suite definitions.

``[server]``
============

.. code-block:: python

    # Password to authenticate hypervisors.
    connection_passwd=some_password
    
    # The IP and port the master will listen on.
    ip=0.0.0.0
    port=20000

``[webserver]``
===============

.. code-block:: python

    # Absolute path to webpage files (defaults to /usr/share/XrdTest/webpage).
    # Uncomment and add your path to change the web root.
    webpage_dir=/usr/share/XrdTest/webpage
    
    # Protocol to use for the web server. Defaults to HTTP.
    protocol=https
    
    # The port to access the web interface on. Defaults to 8080 for HTTP and 8443
    # for HTTPS.
    port=8443
    
    # The password that allows running test suites via the webpage (defaults to none)
    # suite_run_pass=somepass

``[scheduler]``
===============

.. code-block:: python

    # If set to 0, the scheduler will not run, strangely enough.
    enabled=1

``[security]``
==============

.. code-block:: python

    # Location of the master's SSL certificate and private key. Will be generated 
    # automatically at install time. Don't change these.
    certfile=/etc/XrdTest/certs/mastercert.pem
    keyfile=/etc/XrdTest/certs/masterkey.pem
    
    # Location of the key/certificate which the master will use to become it's own
    # CA (for signing CSRs from slaves which need to use GSI).
    ca_certfile=/etc/XrdTest/certs/cacert.pem
    ca_keyfile=/etc/XrdTest/certs/cakey.pem
    
``[daemon]``
============
    
.. code-block:: python

    # Path to PID file if being run in daemon mode.
    pid_file_path=/var/run/XrdTestMaster.pid
    
    # Path the the master's log file.
    log_file_path=/var/log/XrdTest/XrdTestMaster.log
    
    # Amount of information to log. Constants from standard python logging module.
    # Defaults to INFO. Possible values: NOTSET (off), ERROR (only errors), WARN
    # (warnings and above), INFO (most logs), DEBUG (everything)
    log_level=DEBUG 
    
Other considerations
--------------------

* Firewall (tcp on port 10000)
