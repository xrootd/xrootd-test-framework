*************
Configuration
*************

Default place for configuration files is directory: /etc/XrdTest/<CONFIG_FILE_NAME>.conf

Running as a system service (daemons)
-------------------------------------

If application was installed from RPM it is automatically added to system 
services, thus it will be started automatically during the system start, but 
can also be started manually from the command line as follows:

``service COMPONENT_NAME start``

where the COMPONENT_NAME is accordingly

* for master: ``xrdtest-master``
* for slave: ``xrdtest-slave``
* for hypervisor: ``xrdtest-hypervisor``

Running in debug mode
---------------------

To start each of components (Master, Hypervisor or Slave) in debug mode (it 
shows log messages on the screen instead of writing them to log file) run the 
shell command below::

    # export PYTHONPATH=<PROJECT_DIR>/lib
    # cd <PROJECT_DIR>
    # python XrdTestMaster.py -c XrdTestMaster.conf
    
Where <PROJECT_DIR> should be replaced with actual directory where framework 
source .py files are stored. One can start Hypervisor or Slave replacing 
XrdTestMaster with XrdTestHypervisor or XrdTestSlave accordingly.

Running in background mode
--------------------------

To start application in background mode (as a daemon) add option -b to shell 
starting command. Itwill then store LOG file and PID file in proper directories 
specified in configuration files. Go to directory where application is stored 
and run::
    
    # python XrdTestMaster.py -d -c XrdTestMaster.conf

