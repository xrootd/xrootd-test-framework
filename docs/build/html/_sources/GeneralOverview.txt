General Overview
================

* Framework Components
    * :ref:`master`
    * :ref:`Hypervisor`
    * :ref:`Slave`

.. _master:

Master
------

Module file: XrdTestMaster.py

Master is the user entry point for the testing framework. The service is configured via config file and
exports a web service showing the current statistics of the service as well as the status of the tests that
are being run and have been run in the past. 
It accepts connections from Slave and Hypervisor daemons and dispatches commands to them.

Quick summary:
user entry point to the framework
supervise and synchronize all system activities
accepts connections from Slaves and Hypervisors and dispatches commands to them
is run as a system service (daemon), configured via batch of configuration files

.. _hypervisor:

Hypervisor
----------

Module file: XrdTestHypervisor.py
Daemon which receives the machines and network configurations from the Master and
starts/stops/configures the virtual machines accordingly. It uses Qemu with the KVM
kernel module
in Linux and libvirt virtualization library to as a layer to communicate with Qemu.
Quick summary:
application to manage the virtual machines clusters and networks on demand of M
aster
is run as a system service (daemon), configured via configuration file
it starts/stops/configures virtual machines
uses libvirt for managing virtual machines

.. _slave:

Slave
-----

Module file: XrdTestSlave.py
Daemon installed on virtual or physical machines that runs the actual tests. In the first iteration it is
supposed to receive a bunch of shell scripts from the M
aster and run them. It connects to M
aster
automatically, having by its name (Hipervisor redirects it by IP or master's address is known
because user provides it while starting).
Quick summary:
the actual application which runs tests
may be running on virtual or physical machines
is run as a system service (daemon), configured via configurationfile
it receives test cases from Master and runs them synchronously with other Slaves

