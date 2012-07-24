#!/bin/sh
mkdir -p tmp_initsh
rm -rf tmpinitsh/*
cd tmp_initsh
wget "http://vagabond.cern.ch:8080/getGetXrdLastReleaseScript" -O getXrdLastReleaseScript.py
chmod 755 getXrdLastReleaseScript.py
rm -rf xrd_rpms
python getXrdLastReleaseScript.py
ls xrd_rpms
rm -rf xrd_rpms/xrootd-*.src.*.rpm
rm -rf xrd_rpms/xrootd-*-devel-*.rpm
rpm -i xrd_rpms/xrootd-libs-*.rpm
rpm -i xrd_rpms/xrootd-client-*.rpm
rpm -i xrd_rpms/xrootd-fuse-*.rpm
rpm -i xrd_rpms/xrootd-server-*.rpm
cd ..
