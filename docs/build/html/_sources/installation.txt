Installation
============

The framework is available in RPM packages for Linux SLC6. Each application 
requires at least Python ``2.4``. It comprises the following four main packages 
(the libraries required by them are also listed below):

* **xrdtest-lib** 
  
  Dependencies: None

* **xrdtest-master** 
  
  Dependencies: 
    * ``python-apscheduler-2.0.3`` 
    * ``python-cheetah-2.4.1`` 
    * ``python-cherrypy-3.1.2`` 
    * ``python-inotify-0.9.1`` 
    * ``python-uuid-1.30``
    * ``pyOpenSSL-0.10-2``
    * ``python-ssl-1.15`` 

* **xrdtest-hypervisor**
  
  Dependencies: 
    * ``python-ssl-1.15`` 
    * ``libvirt-python-0.9.3`` 
    * ``libvirt-0.9.10``

* **xrdtest-slave** 
  
  Dependencies: 
    * ``python-ssl-1.15``

To install each component, you must follow typical RPM installation instructions.
