# %{!?python_sitelib: %define python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}
%define python_sitelib /usr/lib/python2.6/site-packages

Name:           xrdtest
Version:        0.0.1
Release:        1%{?dist}
License:        GPL3
Summary:        Xrootd Testing Framework consists of 4 components (packages): test master, test slave, test hypervisor and a library package.
Group:          Development/Tools
Packager:       Justin Salmon <jsalmon@cern.ch>
URL:            http://xrootd.cern.ch/cgi-bin/cgit.cgi/xrootd-tests/
Source0:        %{name}-%{version}.tar.gz
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
BuildArch:      noarch
Requires:       python >= 2.4

%description
Xrootd Testing Framework consists of 4 components (packages): test master, test slave, test hypervisor and a library package.

%prep
%setup

#-------------------------------------------------------------------------------
# Install section
#-------------------------------------------------------------------------------
%install
[ "x%{buildroot}" != "x/" ] && rm -rf %{buildroot}
%define libs_path %{buildroot}%{python_sitelib}/XrdTest

# libs
mkdir -p %{libs_path}
install -pm 644 src/XrdTest/*.py %{libs_path}

# logs
mkdir -p %{buildroot}%{_localstatedir}/log/XrdTest

# init scripts
mkdir -p %{buildroot}%{_initrddir}
install -pm 755 packaging/rpm/xrdtest-master.init %{buildroot}%{_initrddir}/xrdtest-master
install -pm 755 packaging/rpm/xrdtest-hypervisor.init %{buildroot}%{_initrddir}/xrdtest-hypervisor
install -pm 755 packaging/rpm/xrdtest-slave.init %{buildroot}%{_initrddir}/xrdtest-slave

# configs
mkdir -p %{buildroot}%{_sysconfdir}/XrdTest
mkdir -p %{buildroot}%{_sysconfdir}/XrdTest/test-suites
mkdir -p %{buildroot}%{_sysconfdir}/XrdTest/clusters
mkdir -p %{buildroot}%{_sysconfdir}/XrdTest/certs
mkdir -p %{buildroot}%{_sbindir}

install -pm 755 src/XrdTestMaster.py %{buildroot}%{_sbindir}
install -pm 644 src/conf/XrdTestMaster.conf %{buildroot}%{_sysconfdir}/XrdTest
install -pm 755 src/XrdTestHypervisor.py %{buildroot}%{_sbindir}
install -pm 644 src/conf/XrdTestHypervisor.conf %{buildroot}%{_sysconfdir}/XrdTest
install -pm 755 src/XrdTestSlave.py %{buildroot}%{_sbindir}
install -pm 644 src/conf/XrdTestSlave.conf %{buildroot}%{_sysconfdir}/XrdTest

# webpage
mkdir -p %{buildroot}%{_datadir}/XrdTest
cp -r src/webpage %{buildroot}%{_datadir}/XrdTest

#-------------------------------------------------------------------------------
# XrdTestLib
#-------------------------------------------------------------------------------
%package lib

Summary: Shared library files for XrdTestFramework.
Group:   Development/Tools
Requires: python >= 2.4

%description lib
Shared library files for XrdTestFramework.

%files lib
%defattr(-,root,root,-)
%{python_sitelib}/XrdTest

#-------------------------------------------------------------------------------
# XrdTestMaster
#-------------------------------------------------------------------------------
%package master

Summary: Xrd Test Master is component of XrdTestFramework.
Group:   Development/Tools
Requires: python >= 2.4
Requires: xrdtest-lib
Requires: python-apscheduler, python-uuid, python-cherrypy, python-cheetah, python-inotify, openssl, pyOpenSSL

%description master
Xrd Test Master is component of XrdTestFramework.
%files master
%defattr(-,root,root,-)

%attr(0400, root, root) %config(noreplace) %{_sysconfdir}/XrdTest/XrdTestMaster.conf
%{_sysconfdir}/XrdTest/certs/
%{_sbindir}/XrdTestMaster.py
%{_datadir}/XrdTest/webpage/*
%{_initrddir}/xrdtest-master
%{_localstatedir}/log/XrdTest

#-------------------------------------------------------------------------------
# XrdTestSlave
#-------------------------------------------------------------------------------
%package slave
Summary: Xrd Test Slave is component of XrdTestFramework.
Group:   Development/Tools
Requires: python >= 2.4
Requires: xrdtest-lib, openssl

%description slave
Xrd Test Slave is component of XrdTestFramework. It runs tests provided by Xrd Test Master on virtual or physical machines.
%files slave
%defattr(-,root,root,-)

%attr(0400, root, root) %config(noreplace) %{_sysconfdir}/XrdTest/XrdTestSlave.conf
%{_sysconfdir}/XrdTest/certs/
%{_sbindir}/XrdTestSlave.py
%{_initrddir}/xrdtest-slave
%{_localstatedir}/log/XrdTest

#-------------------------------------------------------------------------------
# XrdTestHypervisor
#-------------------------------------------------------------------------------
%package hypervisor
Summary: Xrd Test Hypervisor is component of XrdTestFramework.
Requires: python >= 2.4
Requires: libvirt >= 0.9.3, libvirt-python >= 0.9.3
Requires: xrdtest-lib, openssl

Group:	 Development/Tools
%description hypervisor
Xrd Test Hypervisor is component of XrdTestFramework. It manages virtual machines clusters, on master's requests.
%files hypervisor
%defattr(-,root,root,-)

%attr(0400, root, root) %config(noreplace) %{_sysconfdir}/XrdTest/XrdTestHypervisor.conf
%{_sysconfdir}/XrdTest/certs/
%{_sbindir}/XrdTestHypervisor.py
%{_initrddir}/xrdtest-hypervisor
%{_localstatedir}/log/XrdTest

%clean
[ "x%{buildroot}" != "x/" ] && rm -rf %{buildroot}

#-------------------------------------------------------------------------------
# Install rc*.d links and create SSL certs
#-------------------------------------------------------------------------------
%post master
/sbin/ldconfig
/sbin/chkconfig --add xrdtest-master
if [ ! -f %{_sysconfdir}/XrdTest/certs/masterkey.pem ] 
then
  openssl genrsa -out %{_sysconfdir}/XrdTest/certs/masterkey.pem 2048
  openssl req -new -batch -x509 -key %{_sysconfdir}/XrdTest/certs/masterkey.pem -out %{_sysconfdir}/XrdTest/certs/mastercert.pem -days 1095
fi

%preun master
/sbin/service xrdtest-master stop
/sbin/chkconfig --del xrdtest-master

%postun master
/sbin/ldconfig
if [ "$1" -ge "1" ] ; then
    /sbin/service xrdtest-master condrestart
fi

#-------------------------------------------------------------------------------

%post slave
/sbin/ldconfig
/sbin/chkconfig --add xrdtest-slave
if [ ! -f %{_sysconfdir}/XrdTest/certs/slavekey.pem ]
then
  openssl genrsa -out %{_sysconfdir}/XrdTest/certs/slavekey.pem 2048
  openssl req -new -batch -x509 -key %{_sysconfdir}/XrdTest/certs/slavekey.pem -out %{_sysconfdir}/XrdTest/certs/slavecert.pem -days 1095
fi

%preun slave
service xrdtest-slave stop
/sbin/chkconfig --del xrdtest-slave

%postun slave
/sbin/ldconfig
if [ "$1" -ge "1" ] ; then
    /sbin/service xrdtest-slave condrestart
fi

#-------------------------------------------------------------------------------

%post hypervisor
/sbin/ldconfig
/sbin/chkconfig --add xrdtest-hypervisor
if [ ! -f %{_sysconfdir}/XrdTest/certs/hypervisorkey.pem ]
then
  openssl genrsa -out %{_sysconfdir}/XrdTest/certs/hypervisorkey.pem 2048
  openssl req -new -batch -x509 -key %{_sysconfdir}/XrdTest/certs/hypervisorkey.pem -out %{_sysconfdir}/XrdTest/certs/hypervisorcert.pem -days 1095
fi

%preun hypervisor
service xrdtest-hypervisor stop
/sbin/chkconfig --del xrdtest-hypervisor

%postun hypervisor
/sbin/ldconfig
if [ "$1" -ge "1" ] ; then
    /sbin/service xrdtest-hypervisor condrestart
fi

#-------------------------------------------------------------------------------

%changelog
* Thu Jul 5 2012 Justin Salmon <jsalmon@cern.ch>
- Edited to build new folder structure
* Wed Feb 15 2012 Lukasz Trzaska <ltrzaska@cern.ch>
- initial package
