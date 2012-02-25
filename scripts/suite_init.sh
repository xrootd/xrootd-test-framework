#!/bin/sh
mkdir -p tmp_initsh
rm -rf tmpinitsh/*
cd tmp_initsh
wget "localhost:8080/getGetXrdLastReleaseScript" -O get_rpms.py
chmod 755 get_rpms.py
rm -rf xrd_rpms
python get_rpms.py
ls xrd_rpms
rm -rf xrd_rpms/slc-5-i386/xrootd-libs-devel*.i386.rpm
rpm -i xrd_rpms/slc-5-i386/xrootd-libs-*.i386.rpm
rm -rf xrd_rpms/slc-5-i386/xrootd-client-devel*.i386.rpm
rpm -i xrd_rpms/slc-5-i386/xrootd-client-*.i386.rpm
rm -rf xrd_rpms/slc-5-i386/xrootd-server-devel*.i386.rpm
rpm -i xrd_rpms/slc-5-i386/xrootd-server-*.i386.rpm
