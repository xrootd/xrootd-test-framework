#!/bin/sh
generuj_blad
mkdir -p tmp_initsh
rm -rf tmpinitsh/*
cd tmp_initsh
wget "http://master.xrd.test:8080/getGetXrdLastReleaseScript" -O getXrdLastReleaseScript.py
chmod 755 getXrdLastReleaseScript.py
rm -rf xrd_rpms
python getXrdLastReleaseScript.py
ls xrd_rpms
rm -rf xrd_rpms/slc-5-x86_64/xrootd-*.src.*.rpm
rm -rf xrd_rpms/slc-5-x86_64/xrootd-*-devel-*.rpm
rpm -i xrd_rpms/slc-5-x86_64/xrootd-*.rpm
cd ..
