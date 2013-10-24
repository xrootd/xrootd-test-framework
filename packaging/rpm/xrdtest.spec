#-------------------------------------------------------------------------------
# Global defs
#-------------------------------------------------------------------------------
%{!?python_sitelib: %define python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}

Name:           xrdtest
Version:        0.2
Release:        6%{?dist}
License:        GPL3
Summary:        Xrootd Testing Framework
Group:          Development/Tools
Packager:       Justin Salmon <jsalmon@cern.ch>
URL:            http://xrootd.cern.ch/cgi-bin/cgit.cgi/xrootd-tests/
Source0:        %{name}-%{version}.tar.gz
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
BuildArch:      noarch
Requires:       python >= 2.4

%description
Xrootd Testing Framework.

#-------------------------------------------------------------------------------
# XrdTestLib
#-------------------------------------------------------------------------------
%package lib

Summary: Shared library files for XrdTestFramework.
Group:   Development/Tools
Requires: python >= 2.4

%description lib
Shared library files for XrdTestFramework.

#-------------------------------------------------------------------------------
# XrdTestMaster
#-------------------------------------------------------------------------------
%package master

Summary: Xrd Test Master is component of XrdTestFramework.
Group:   Development/Tools
Requires: python >= 2.4
Requires: xrdtest-lib
Requires: python-apscheduler, python-uuid, python-cherrypy, python-cheetah,
Requires: python-inotify, openssl, pyOpenSSL

%description master
Xrd Test Master is component of XrdTestFramework.

#-------------------------------------------------------------------------------
# XrdTestHypervisor
#-------------------------------------------------------------------------------
%package hypervisor
Summary: Xrd Test Hypervisor is component of XrdTestFramework.
Requires: python >= 2.4
Requires: libvirt >= 0.9.3, libvirt-python >= 0.9.3
Requires: xrdtest-lib, openssl
Group:     Development/Tools

%description hypervisor
Xrd Test Hypervisor is component of XrdTestFramework. It manages virtual
machines clusters, on master requests.

#-------------------------------------------------------------------------------
# XrdTestSlave
#-------------------------------------------------------------------------------
%package slave
Summary: Xrd Test Slave is component of XrdTestFramework.
Group:   Development/Tools
Requires: python >= 2.4
Requires: xrdtest-lib, openssl

%description slave
Xrd Test Slave is component of XrdTestFramework. It runs tests provided by Xrd
Test Master on virtual or physical machines.

#-------------------------------------------------------------------------------
# Install section
#-------------------------------------------------------------------------------
%prep
%setup

%install
[ "x%{buildroot}" != "x/" ] && rm -rf %{buildroot}
%define libs_path %{buildroot}%{python_sitelib}/XrdTest

# libs
mkdir -p %{libs_path}
install -pm 644 src/XrdTest/*.py %{libs_path}

# logs
mkdir -p %{buildroot}%{_localstatedir}/log/XrdTest
mkdir -p %{buildroot}%{_localstatedir}/run/XrdTest
mkdir -p %{buildroot}%{_localstatedir}/lib/XrdTest
mkdir -p %{buildroot}%{_localstatedir}/cache/XrdTest

# init scripts
mkdir -p %{buildroot}%{_initrddir}
install -pm 755 packaging/rpm/xrdtest-master.init %{buildroot}%{_initrddir}/xrdtest-master
install -pm 755 packaging/rpm/xrdtest-hypervisor.init %{buildroot}%{_initrddir}/xrdtest-hypervisor
install -pm 755 packaging/rpm/xrdtest-slave.init %{buildroot}%{_initrddir}/xrdtest-slave

# configs
mkdir -p %{buildroot}%{_sysconfdir}/XrdTest
mkdir -p %{buildroot}%{_sysconfdir}/XrdTest/certs
mkdir -p %{buildroot}%{_sysconfdir}/XrdTest/utils
mkdir -p %{buildroot}%{_sbindir}

install -pm 755 src/XrdTestMaster.py %{buildroot}%{_sbindir}
install -pm 644 src/conf/XrdTestMaster.conf %{buildroot}%{_sysconfdir}/XrdTest
install -pm 755 src/XrdTestHypervisor.py %{buildroot}%{_sbindir}
install -pm 644 src/conf/XrdTestHypervisor.conf %{buildroot}%{_sysconfdir}/XrdTest
install -pm 755 src/XrdTestSlave.py %{buildroot}%{_sbindir}
install -pm 644 src/conf/XrdTestSlave.conf %{buildroot}%{_sysconfdir}/XrdTest
install -pm 755 utils/functions.sh %{buildroot}%{_sysconfdir}/XrdTest/utils

# webpage
mkdir -p %{buildroot}%{_datadir}/XrdTest
cp -r src/webpage %{buildroot}%{_datadir}/XrdTest

# docs
cp -r docs %{buildroot}%{_datadir}/XrdTest/webpage

%clean
[ "x%{buildroot}" != "x/" ] && rm -rf %{buildroot}

#-------------------------------------------------------------------------------
# Files lib
#-------------------------------------------------------------------------------
%files lib
%defattr(-,root,root,-)
%{python_sitelib}/XrdTest
%{_datadir}/XrdTest/webpage/*

#-------------------------------------------------------------------------------
# File master
#-------------------------------------------------------------------------------
%files master
%defattr(-,root,root,-)
%config(noreplace) %{_sysconfdir}/XrdTest/XrdTestMaster.conf
%attr(-,daemon,daemon) %dir %{_sysconfdir}/XrdTest/certs/
%{_sbindir}/XrdTestMaster.py
%{_datadir}/XrdTest/webpage/*
%{_initrddir}/xrdtest-master
%attr(-,daemon,daemon) %dir %{_localstatedir}/log/XrdTest
%attr(-,daemon,daemon) %dir %{_localstatedir}/lib/XrdTest
%attr(-,daemon,daemon) %dir %{_localstatedir}/run/XrdTest
%attr(-,daemon,daemon) %dir %{_localstatedir}/cache/XrdTest

#-------------------------------------------------------------------------------
# Files slave
#-------------------------------------------------------------------------------
%files slave
%defattr(-,root,root,-)
%config(noreplace) %{_sysconfdir}/XrdTest/XrdTestSlave.conf
%{_sysconfdir}/XrdTest/certs/
%{_sysconfdir}/XrdTest/utils/
%{_sbindir}/XrdTestSlave.py
%{_initrddir}/xrdtest-slave
%dir %{_localstatedir}/log/XrdTest
%dir %{_localstatedir}/run/XrdTest

#-------------------------------------------------------------------------------
# Files hypervisor
#-------------------------------------------------------------------------------
%files hypervisor
%defattr(-,root,root,-)
%config(noreplace) %{_sysconfdir}/XrdTest/XrdTestHypervisor.conf
%{_sysconfdir}/XrdTest/certs/
%{_sbindir}/XrdTestHypervisor.py
%{_initrddir}/xrdtest-hypervisor
%dir %{_localstatedir}/log/XrdTest
%dir %{_localstatedir}/run/XrdTest

#-------------------------------------------------------------------------------
# Scriptlets master
#-------------------------------------------------------------------------------
%post master
if [ $1 -eq 1 ]; then
  /sbin/chkconfig --add xrdtest-master
fi

if [ ! -f %{_sysconfdir}/XrdTest/certs/masterkey.pem ] 
then
  openssl genrsa -out %{_sysconfdir}/XrdTest/certs/masterkey.pem 2048
  openssl req -new -batch -x509 -key %{_sysconfdir}/XrdTest/certs/masterkey.pem -out %{_sysconfdir}/XrdTest/certs/mastercert.pem -days 1095
  chown daemon:root -R %{_sysconfdir}/XrdTest/certs
fi

%preun master
if [ $1 -eq 0 ]; then
  /sbin/service xrdtest-master stop
  /sbin/chkconfig --del xrdtest-master
fi

%postun master
if [ "$1" -ge "1" ] ; then
  /sbin/service xrdtest-master condrestart
fi

#-------------------------------------------------------------------------------
# Scriptlets slave
#-------------------------------------------------------------------------------
%post slave
if [ $1 -eq 1 ]; then
  /sbin/chkconfig --add xrdtest-slave
fi

if [ ! -f %{_sysconfdir}/XrdTest/certs/slavekey.pem ]; then
  openssl genrsa -out %{_sysconfdir}/XrdTest/certs/slavekey.pem 2048
  openssl req -new -batch -x509 -key %{_sysconfdir}/XrdTest/certs/slavekey.pem -out %{_sysconfdir}/XrdTest/certs/slavecert.pem -days 1095
fi

%preun slave
if [ $1 -eq 0 ]; then
  service xrdtest-slave stop
  /sbin/chkconfig --del xrdtest-slave
fi

%postun slave
if [ "$1" -ge "1" ] ; then
  /sbin/service xrdtest-slave condrestart
fi

#-------------------------------------------------------------------------------
# Scriptlets hypervisor
#-------------------------------------------------------------------------------
%post hypervisor
if [ $1 -eq 1 ]; then
  /sbin/chkconfig --add xrdtest-hypervisor
fi

if [ ! -f %{_sysconfdir}/XrdTest/certs/hypervisorkey.pem ]
then
  openssl genrsa -out %{_sysconfdir}/XrdTest/certs/hypervisorkey.pem 2048
  openssl req -new -batch -x509 -key %{_sysconfdir}/XrdTest/certs/hypervisorkey.pem -out %{_sysconfdir}/XrdTest/certs/hypervisorcert.pem -days 1095
fi

%preun hypervisor
if [ $1 -eq 0 ]; then
  service xrdtest-hypervisor stop
  /sbin/chkconfig --del xrdtest-hypervisor
fi

%postun hypervisor
if [ "$1" -ge "1" ] ; then
  /sbin/service xrdtest-hypervisor condrestart
fi

#-------------------------------------------------------------------------------
# Changelog
#-------------------------------------------------------------------------------
%changelog
* Wed Oct 23 2014 Lukasz Janyst <ljanyst@cern.ch>
- Refactor slightly and fix the scriptlets
* Thu May 30 2013 Justin Salmon <jsalmon@cern.ch>
- Tag version 0.2
* Tue Oct 16 2012 Justin Salmon <jsalmon@cern.ch>
- Added util scripts for slave
* Tue Sep 11 2012 Justin Salmon <jsalmon@cern.ch>
- Tagged as v0.1
* Thu Jul 5 2012 Justin Salmon <jsalmon@cern.ch>
- Edited to build new folder structure
* Wed Feb 15 2012 Lukasz Trzaska <ltrzaska@cern.ch>
- initial package
