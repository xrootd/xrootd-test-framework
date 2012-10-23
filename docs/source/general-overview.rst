****************
General Overview
****************

The XrdTest Framework is comprised of 3 main components:

* :ref:`master`
* :ref:`hypervisor`
* :ref:`slave`
    
Each of which is explained in more detail below.

.. _master:

Master
------

Module file: ``XrdTestMaster.py``

The master is the user entry point for the testing framework. The service is 
configured via a *ini*-style configuration file (see :doc:`config-master`).

It includes a web interface showing the current statistics of the service,
as well as the status of the tests that are being run and have been run in the 
past (see :doc:`web-interface`). 

It accepts connections from slave and hypervisor daemons and dispatches commands 
to them. The master is responsible for running,  orchestrating and synchronizing 
test suites.

Quick summary:

* User entry point to the framework
* Supervises and synchronizes all system activities
* Accepts connections from slaves and hypervisors and dispatches commands to 
  them
* Runs as a system service (daemon), configured via batch of configuration files

.. _hypervisor:

Hypervisor
----------

Module file: ``XrdTestHypervisor.py``

The hypervisor receives cluster configurations from the master and starts/stops
/configures the virtual machines which make up the cluster accordingly,
including configuring the virtual network with which the slaves use to 
communicate. It uses ``qemu`` with the ``kvm`` kernel module in Linux 
and the ``libvirt`` virtualization API as a layer to communicate with 
``qemu``.

Quick summary:

* Component to manage clusters of virtual machines on demand of the master
* It is run as a system service (daemon), configured via configuration file 
  (see :doc:`config-hypervisor`)
* Starts/stops/configures virtual machines
* Uses ``libvirt`` for managing virtual machines

.. _slave:

Slave
-----

Module file: ``XrdTestSlave.py``

The slave component is installed on virtual or physical machines, and runs the 
actual tests. In the first iteration it will receive a bunch of shell scripts 
from the master and run them. Slaves connect to the master automatically, made 
possible by libvirt's use of dnsmasq.

Quick summary:

* The component which actually runs tests
* May be running on virtual or physical machines
* Runs as a system service (daemon), configured via configuration file (see
  :doc:`config-slave`)
* Receives test cases from the master and runs them synchronously with other 
  slaves


Running as a system service (daemon)
------------------------------------

If the application was installed from an RPM, it is automatically added to the
system services (via ``chkconfig``), thus it will be started automatically 
during system boot. It can also be started manually from the command line as 
follows::

    service COMPONENT_NAME start

where COMPONENT_NAME is accordingly:

* ``xrdtest-master``
* ``xrdtest-slave``
* ``xrdtest-hypervisor``

Running in debug mode
---------------------

.. note::
    The default location for configuration files is 
    ``/etc/XrdTest/<CONFIG_FILE_NAME>.conf``.

To start each component (master, hypervisor or slave) in debug mode, run the 
shell command below::

    python /usr/sbin/XrdTestMaster.py -c XrdTestMaster.conf
    
One can start a hypervisor or a slave by replacing ``XrdTestMaster`` with 
``XrdTestHypervisor`` or ``XrdTestSlave`` accordingly.

When running in debug mode, the component will print log messages to ``stdout``,
rather than writing them to the log file. 

Running in background mode
--------------------------

To start a component in background mode (as a daemon), add the ``-b`` option 
to the shell command. It will then store log and PID files in their proper 
directories, as specified in the configuration file. For example::
    
    # python /usr/sbin/XrdTestMaster.py -d -c XrdTestMaster.conf

