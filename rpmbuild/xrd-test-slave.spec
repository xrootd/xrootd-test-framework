%{!?python_sitelib: %define python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}
# 
Name:           XrdTestSlave
Version:        0.0.1
Release:        1%{?dist}
License:	GNU/GPL
Summary:        XrdTestSlave daemon is client part of a xrootd testing framework.
Group:          Development/Tools
Packager:	Lukasz Trzaska \<ltrzaska@cern.ch\> 
URL:            http://xrootd.org
Source0:        http://xrootd.org/%{name}-%{version}.tar.gz
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
BuildArch:      noarch
Requires: 	python >= 2.4

#%if 0%{?fedora} >= 8
#BuildRequires: python-setuptools-devel
#%else
#BuildRequires: python-setuptools
#%endif
 
%description
XRootD testing framework, client's daemon application.
 
%install
#[ "%{buildroot}" != "/" ] && rm -rf %{buildroot}
#%{__python} -c 'import setuptools; execfile("setup.py")' install -O1 --skip-build --root %{buildroot}
%define libs_path %{buildroot}%{python_sitelib}/XrdTest

mkdir -p %{libs_path}
install -m 755 ./lib/{Utils,TestUtils,SocketUtils,Daemon}.py %{libs_path}
mkdir -p %{buildroot}etc/XrdTest
install -m 755 ./XrdTestSlave.conf %{buildroot}etc/XrdTest
 
#%clean
#[ "%{buildroot}" != "/" ] && rm -rf %{buildroot}
 
%files
%defattr(-,root,root,-)
%doc REPLACE 
%{python_sitelib}/%{name}
 
%changelog
* Wed Feb 15 2012 Lukasz Trzaska <ltrzaska@cern.ch>
- initial package
