#!/bin/bash

echo -ne `date` @slavename@ "Initializing test suite\n"

mkdir -p tmp_initsh
rm -rf tmpinitsh/*
cd tmp_initsh
wget "http://master.xrd.test:8080/showScript/lib/get_xrd_latest.py" -O get_xrd_latest.py
chmod 755 get_xrd_latest.py
rm -rf xrd_rpms
python get_xrd_latest.py
ls xrd_rpms
rm -rf xrd_rpms/slc-6-x86_64/xrootd-*.src.*.rpm
rm -rf xrd_rpms/slc-6-x86_64/xrootd-*-devel-*.rpm
rpm -i xrd_rpms/slc-6-x86_64/xrootd-libs-*.rpm
rpm -i xrd_rpms/slc-6-x86_64/xrootd-client-*.rpm
rpm -i xrd_rpms/slc-6-x86_64/xrootd-fuse-*.rpm
rpm -i xrd_rpms/slc-6-x86_64/xrootd-server-*.rpm
cd ..
