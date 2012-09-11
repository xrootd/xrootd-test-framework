%{!?python_sitelib: %define python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}

#-------------------------------------------------------------------------------
# Advanced Python Scheduler 2.0.3
#-------------------------------------------------------------------------------
Name:           python-apscheduler
Version:        2.0.3
Release:        1%{?dist}
License:    GNU/GPL
Summary:    Advanced Python Scheduler (APScheduler) is a light but powerful in-process task scheduler.
Group:        Development/Tools
Packager:    Lukasz Trzaska <ltrzaska@cern.ch>
URL:            http://pypi.python.org/pypi/APScheduler
Source0:        http://pypi.python.org/packages/source/A/APScheduler/APScheduler-2.0.3.tar.gz
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
BuildArch:      noarch
Requires:     python >= 2.4

%description
Advanced Python Scheduler (APScheduler) is a light but powerful in-process task scheduler that lets you schedule functions to be executed at times of your choosing.

%prep
%setup -n APScheduler-2.0.3

#-------------------------------------------------------------------------------
# Install section
#-------------------------------------------------------------------------------
%install
[ "x%{buildroot}" != "x/" ] && rm -rf %{buildroot}

mkdir -p %{buildroot}%{python_sitelib}
cp -r apscheduler %{buildroot}%{python_sitelib}
chmod --recursive 755 %{buildroot}%{python_sitelib}/apscheduler

%files
%defattr(-,root,root,755)
%{python_sitelib}/apscheduler

%clean
[ "x%{buildroot}" != "x/" ] && rm -rf %{buildroot}
