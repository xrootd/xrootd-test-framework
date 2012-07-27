#!/bin/bash

echo -ne `date` @slavename@ "Initializing test suite\n"

mkdir -p tmp_initsh
rm -rf tmpinitsh/*
cd tmp_initsh
wget "http://master.xrd.test:8080/showScript/lib/get_xrd_latest.py" -O get_xrd_latest.py
chmod 755 get_xrd_latest.py
rm -rf xrd_rpms
python get_xrd_latest.py
echo "#-------------------------------------------------------------------------"
ls xrd_rpms
rm -rf xrd_rpms/slc-6-x86_64/xrootd-*.src.*.rpm
rm -rf xrd_rpms/slc-6-x86_64/xrootd-*-devel-*.rpm


echo "# Installing xrootd-libs"
rpm -iv --force xrd_rpms/slc-6-x86_64/xrootd-libs-*.rpm
echo "#-------------------------------------------------------------------------"
echo "# Installing xrootd-client"
rpm -iv --force xrd_rpms/slc-6-x86_64/xrootd-client-*.rpm
echo "#-------------------------------------------------------------------------"
echo "# Installing xrootd-client-admin-perl"
rpm -iv --force xrd_rpms/slc-6-x86_64/xrootd-client-admin-perl-*.rpm
echo "#-------------------------------------------------------------------------"
echo "# Installing xrootd-fuse"
rpm -iv --force xrd_rpms/slc-6-x86_64/xrootd-fuse-*.rpm
echo "#-------------------------------------------------------------------------"
echo "# Installing xrootd-server"
rpm -iv --force xrd_rpms/slc-6-x86_64/xrootd-server-*.rpm
echo "#-------------------------------------------------------------------------"
rpm -qa | grep xrootd
cd ..
