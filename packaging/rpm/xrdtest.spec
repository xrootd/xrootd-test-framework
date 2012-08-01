# %{!?python_sitelib: %define python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}
%define python_sitelib /usr/lib/python2.6/site-packages

Name:           xrdtest
Version:        0.0.1
Release:        1%{?dist}
License:	GPL3
Summary:        Xrootd Testing Framework consists of 4 components (packages): test master, test slave, test hypervisor and a library package.
Group:          Development/Tools
Packager:	Justin Salmon <jsalmon@cern.ch>
URL:            http://xrootd.cern.ch/cgi-bin/cgit.cgi/xrootd-tests/
Source0:        %{name}-%{version}.tar.gz
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
BuildArch:      noarch
Requires: 	python >= 2.4

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
install -pm 755 src/XrdTest/*.py %{libs_path}

# logs
mkdir -p %{buildroot}%{_localstatedir}/log/XrdTest
chmod --recursive 755 %{buildroot}%{_localstatedir}/log/XrdTest

# init scripts
mkdir -p %{buildroot}%{_initrddir}
install -pm 755 packaging/rpm/xrdtestmasterd %{buildroot}%{_initrddir}
install -pm 755 packaging/rpm/xrdtesthypervisord %{buildroot}%{_initrddir}
install -pm 755 packaging/rpm/xrdtestslaved %{buildroot}%{_initrddir}

# configs
mkdir -p %{buildroot}%{_sysconfdir}/XrdTest
mkdir -p %{buildroot}%{_sysconfdir}/XrdTest/test-suites
mkdir -p %{buildroot}%{_sysconfdir}/XrdTest/clusters
mkdir -p %{buildroot}%{_sysconfdir}/XrdTest/certs
mkdir -p %{buildroot}%{_sbindir}

install -pm 755 src/XrdTestMaster.py %{buildroot}%{_sbindir}
install -pm 755 src/conf/XrdTestMaster.conf %{buildroot}%{_sysconfdir}/XrdTest
install -pm 755 src/XrdTestHypervisor.py %{buildroot}%{_sbindir}
install -pm 755 src/conf/XrdTestHypervisor.conf %{buildroot}%{_sysconfdir}/XrdTest
install -pm 755 src/XrdTestSlave.py %{buildroot}%{_sbindir}
install -pm 755 src/conf/XrdTestSlave.conf %{buildroot}%{_sysconfdir}/XrdTest

# SSL certs
openssl genrsa -out %{buildroot}%{_sysconfdir}/XrdTest/certs/masterkey.pem 2048
openssl req -new -batch -x509 -key %{buildroot}%{_sysconfdir}/XrdTest/certs/masterkey.pem -out %{buildroot}%{_sysconfdir}/XrdTest/certs/mastercert.pem -days 1095
openssl genrsa -out %{buildroot}%{_sysconfdir}/XrdTest/certs/hypervisorkey.pem 2048
openssl req -new -batch -x509 -key %{buildroot}%{_sysconfdir}/XrdTest/certs/hypervisorkey.pem -out %{buildroot}%{_sysconfdir}/XrdTest/certs/hypervisorcert.pem -days 1095
openssl genrsa -out %{buildroot}%{_sysconfdir}/XrdTest/certs/slavekey.pem 2048
openssl req -new -batch -x509 -key %{buildroot}%{_sysconfdir}/XrdTest/certs/slavekey.pem -out %{buildroot}%{_sysconfdir}/XrdTest/certs/slavecert.pem -days 1095

# webpage
mkdir -p %{buildroot}%{_datadir}/XrdTest
cp -r src/webpage %{buildroot}%{_datadir}/XrdTest
chmod --recursive 755 %{buildroot}%{_datadir}/XrdTest/webpage

# disk image cache locations
mkdir -p %{buildroot}%{_localstatedir}/lib/libvirt/images/XrdTest
chmod --recursive 777 %{buildroot}%{_localstatedir}/lib/libvirt/images/

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
%defattr(-,root,root,755)
%{python_sitelib}/XrdTest

#-------------------------------------------------------------------------------
# XrdTestMaster
#-------------------------------------------------------------------------------
%package master

Summary: Xrd Test Master is component of XrdTestFramework.
Group:   Development/Tools
Requires: python >= 2.4
Requires: xrdtest-lib
Requires: python-apscheduler, python-uuid, python-cherrypy, python-cheetah, python-inotify, openssl

%description master
Xrd Test Master is component of XrdTestFramework.
%files master
%defattr(-,root,root,755)

%{_sysconfdir}/XrdTest/XrdTestMaster.conf
%{_sysconfdir}/XrdTest/certs/masterkey.pem
%{_sysconfdir}/XrdTest/certs/mastercert.pem
%{_sbindir}/XrdTestMaster.py
%{_datadir}/XrdTest/webpage/*
%{_initrddir}/xrdtestmasterd
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
%defattr(-,root,root,755)

%{_sysconfdir}/XrdTest/XrdTestSlave.conf
%{_sysconfdir}/XrdTest/certs/slavekey.pem
%{_sysconfdir}/XrdTest/certs/slavecert.pem
%{_sbindir}/XrdTestSlave.py
%{_initrddir}/xrdtestslaved
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
%defattr(-,root,root,755)

%{_sysconfdir}/XrdTest/XrdTestHypervisor.conf
%{_sysconfdir}/XrdTest/certs/hypervisorkey.pem
%{_sysconfdir}/XrdTest/certs/hypervisorcert.pem
%{_sbindir}/XrdTestHypervisor.py
%{_initrddir}/xrdtesthypervisord
%{_localstatedir}/log/XrdTest
%{_localstatedir}/lib/libvirt/images/
%{_localstatedir}/lib/libvirt/images/XrdTest

%clean
[ "x%{buildroot}" != "x/" ] && rm -rf %{buildroot}

#-------------------------------------------------------------------------------
# Install rc*.d links
#-------------------------------------------------------------------------------
%post master
/sbin/ldconfig
/sbin/chkconfig --add xrdtestmasterd

%postun master
/sbin/ldconfig

%post slave
/sbin/ldconfig
/sbin/chkconfig --add xrdtestslaved

%postun slave
/sbin/ldconfig

%post hypervisor
/sbin/ldconfig
/sbin/chkconfig --add xrdtesthypervisord

%postun hypervisor
/sbin/ldconfig

%changelog
* Thu Jul 5 2012 Justin Salmon <jsalmon@cern.ch>
- Edited to build new folder structure
* Wed Feb 15 2012 Lukasz Trzaska <ltrzaska@cern.ch>
- initial package
