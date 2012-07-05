#!/bin/bash

if [ -z "$1" ]; then
        echo "usage: create_targz.sh <src_path>"
	exit 0
fi
echo "Copying files from $1"

ARCHIVE_DEST=$PWD
NAME=xrdtest-0.0.1

DEST=${ARCHIVE_DEST}/${NAME}
SRC=$1
CP_OPTS=-r

set -e

mkdir -p ${DEST}/src
mkdir -p ${DEST}/src/XrdTest
mkdir -p ${DEST}/src/conf
mkdir -p ${DEST}/src/webpage
mkdir -p ${DEST}/examples/clusters
mkdir -p ${DEST}/examples/test-suites
mkdir -p ${DEST}/packaging
mkdir -p ${DEST}/packaging/rpm

for n in Slave Master Hypervisor; do
	cp $CP_OPTS ${SRC}/src/XrdTest$n.py ${DEST}/src
	cp $CP_OPTS ${SRC}/src/conf/XrdTest$n.conf ${DEST}/src/conf
done

cp $CP_OPTS ${SRC}/src/webpage ${DEST}/src

cp $CP_OPTS ${SRC}/examples/clusters/*.py ${DEST}/examples/clusters
cp $CP_OPTS ${SRC}/examples/test-suites/*.py ${DEST}/examples/test-suites

cp $CP_OPTS ${SRC}/src/XrdTest/ ${DEST}/src

cp $CP_OPTS ${SRC}/packaging/rpm/xrdtest*d ${DEST}/packaging/rpm

tar -cvzf ${NAME}.tar.gz ${NAME}
rm -rf ${DEST}