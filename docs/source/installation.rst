Installation
============

Framework is available in RPM packages for Linux SLC5. All application requires 
Python 2 in version at least: 2.4. It comprises of the following three main RPMs 
(the libraries required by them are also listed below):

* xrdtest-master-0.0.1-1.noarch
    * required RPMs: **python-apscheduler-2.0.2, python-cheetah-2.0.1, python-cherrypy-2.3.0,
      python-inotify-0.9.1, python-ssl-1.15, python-uuid-1.30**
* xrdtest-hypervisor-0.0.1-1.noarch
    * required RPMs: **python-ssl-1.15, libvirt-python-0.9.3, libvirt-0.9.3**
* xrdtest-slave-0.0.1-1.noarch
    * required RPMs: **python-ssl-1.15**

To install each module you have to follow typical RPM installation instructions.
