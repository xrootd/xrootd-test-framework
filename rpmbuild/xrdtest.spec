%{!?python_sitelib: %define python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}
 
Name:           xrdtest
Version:        0.0.1
Release:        1%{?dist}
License:	GNU/GPL
Summary:        Xrootd Testing Framework consists of 3 components (packages): Test Master, Test Slave and Test Hypervisor.
Group:          Development/Tools
Packager:	Lukasz Trzaska <ltrzaska@cern.ch>
URL:            http://xrootd.cern.ch/cgi-bin/cgit.cgi/xrootd-tests/
Source0:        %{name}-%{version}.tar.gz
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
BuildArch:      noarch
Requires: 	python >= 2.4
Requires:	python-ssl

%description
Xrootd Testing Framework consists of 3 components (packages): Test Master, Test Slave and Test Hypervisor.

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
install -pm 755 lib/Utils.py %{libs_path}
install -pm 755 lib/SocketUtils.py %{libs_path}
install -pm 755 lib/Daemon.py %{libs_path}
install -pm 755 lib/TestUtils.py %{libs_path}

#logs
mkdir -p %{buildroot}%{_localstatedir}\log\XrdTest
chmod --recursive 755 %{buildroot}%{_localstatedir}\log\XrdTest

#init scripts
mkdir -p %{buildroot}%{_initrddir}
install -pm 755 rpmbuild/xrdtestmasterd %{buildroot}%{_initrddir}
install -pm 755 rpmbuild/xrdtesthypervisord %{buildroot}%{_initrddir}
install -pm 755 rpmbuild/xrdtestslaved %{buildroot}%{_initrddir}

#configs
mkdir -p %{buildroot}%{_sysconfdir}/XrdTest
mkdir -p %{buildroot}%{_sysconfdir}/XrdTest/certs
mkdir -p %{buildroot}%{_sysconfdir}/XrdTest/testSuits
mkdir -p %{buildroot}%{_sysconfdir}/XrdTest/clusters
mkdir -p %{buildroot}%{_sbindir}

install -pm 755 XrdTestSlave.py %{buildroot}%{_sbindir}
install -pm 755 XrdTestSlave.conf %{buildroot}%{_sysconfdir}/XrdTest
install -pm 755 certs/slavecert.pem %{buildroot}%{_sysconfdir}/XrdTest/certs
install -pm 755 certs/slavekey.pem %{buildroot}%{_sysconfdir}/XrdTest/certs

install -pm 755 XrdTestMaster.py %{buildroot}%{_sbindir}
install -pm 755 XrdTestMaster.conf %{buildroot}%{_sysconfdir}/XrdTest
install -pm 755 certs/mastercert.pem %{buildroot}%{_sysconfdir}/XrdTest/certs
install -pm 755 certs/masterkey.pem %{buildroot}%{_sysconfdir}/XrdTest/certs

mkdir -p %{buildroot}%{_datadir}/XrdTest
cp -r webpage %{buildroot}%{_datadir}/XrdTest
chmod --recursive 755 %{buildroot}%{_datadir}/XrdTest/webpage

install -pm 755 XrdTestHypervisor.py %{buildroot}%{_sbindir}
install -pm 755 XrdTestHypervisor.conf %{buildroot}%{_sysconfdir}/XrdTest
install -pm 755 certs/hypervisorcert.pem %{buildroot}%{_sysconfdir}/XrdTest/certs
install -pm 755 certs/hypervisorkey.pem %{buildroot}%{_sysconfdir}/XrdTest/certs
install -pm 755 lib/ClusterManager.py %{libs_path}

#-------------------------------------------------------------------------------
# XrdTestMaster
#-------------------------------------------------------------------------------
%package master

Summary: Xrd Test Master is component of XrdTestFramework.
Group:   Development/Tools
Requires: python >= 2.4
Requires: python-ssl
Requires: python-apscheduler, python-uuid, python-cherrypy, python-cheetah, python-inotify

%description master
Xrd Test Master is component of XrdTestFramework.
%files master
%defattr(-,root,root,755)
%{python_sitelib}/XrdTest
%{_sysconfdir}/XrdTest/certs/mastercert.pem
%{_sysconfdir}/XrdTest/certs/masterkey.pem
%{_sysconfdir}/XrdTest/XrdTestMaster.conf
%{_sbindir}/XrdTestMaster.py
%{_sbindir}/XrdTestMaster.pyc
%{_sbindir}/XrdTestMaster.pyo
%{_datadir}/XrdTest/webpage/*
%{_initrddir}/xrdtestmasterd

#-------------------------------------------------------------------------------
# XrdTestSlave
#-------------------------------------------------------------------------------
%package slave
Summary: Xrd Test Slave is component of XrdTestFramework.
Group:   Development/Tools
Requires: python >= 2.4
Requires: python-ssl

%description slave
Xrd Test Slave is component of XrdTestFramework. It runs tests provided by Xrd Test Master on virtual or physical machines.
%files slave
%defattr(-,root,root,755)
%{python_sitelib}/XrdTest
%{_sysconfdir}/XrdTest/certs/slavecert.pem
%{_sysconfdir}/XrdTest/certs/slavekey.pem
%{_sysconfdir}/XrdTest/XrdTestSlave.conf
%{_sbindir}/XrdTestSlave.py
%{_sbindir}/XrdTestSlave.pyc
%{_sbindir}/XrdTestSlave.pyo
%{_initrddir}/xrdtestslaved
#-------------------------------------------------------------------------------
# XrdTestHypervisor
#-------------------------------------------------------------------------------
%package hypervisor
Summary: Xrd Test Hypervisor is component of XrdTestFramework.
Requires: python >= 2.4
Requires: python-ssl
Requires: libvirt >= 0.9.3, libvirt-python >= 0.9.3

Group:	 Development/Tools
%description hypervisor
Xrd Test Hypervisor is component of XrdTestFramework. It manages virtual machines clusters, on master's requests.
%files hypervisor
%defattr(-,root,root,755)
%{python_sitelib}/XrdTest
%{_sysconfdir}/XrdTest/certs/hypervisorcert.pem
%{_sysconfdir}/XrdTest/certs/hypervisorkey.pem
%{_sysconfdir}/XrdTest/XrdTestHypervisor.conf
%{_sbindir}/XrdTestHypervisor.py
%{_sbindir}/XrdTestHypervisor.pyc
%{_sbindir}/XrdTestHypervisor.pyo
%{_initrddir}/xrdtesthypervisord

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
/sbin/chkconfig --del xrdtestmasterd

%post slave
/sbin/ldconfig
/sbin/chkconfig --add xrdtestslaved
%postun slave
/sbin/ldconfig
/sbin/chkconfig --del xrdtestslaved

%post hypervisor
/sbin/ldconfig
/sbin/chkconfig --add xrdtesthypervisord
%postun hypervisor
/sbin/ldconfig
/sbin/chkconfig --del xrdtesthypervisord

%changelog
* Wed Feb 15 2012 Lukasz Trzaska <ltrzaska@cern.ch>
- initial package
