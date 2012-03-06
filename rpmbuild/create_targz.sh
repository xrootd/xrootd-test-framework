#!/bin/bash

ARCHIVE_DEST=$PWD
NAME=XrdTestFramework-0.0.1

DEST=${ARCHIVE_DEST}/${NAME}
SRC=/home/ltrzaska/dev/pydev-workspace/xrd-test/src
CP_OPTS=-vr

mkdir -p ${DEST}
for n in Slave Master Hypervisor; do
	cp $CP_OPTS ${SRC}/XrdTest$n.py ${DEST}
	cp $CP_OPTS ${SRC}/XrdTest$n.conf ${DEST}
done

mkdir -p ${DEST}/certs
for nl in slave master hypervisor; do
	cp $CP_OPTS ${SRC}/certs/${nl}cert.pem ${DEST}/certs
	cp $CP_OPTS ${SRC}/certs/${nl}key.pem ${DEST}/certs
done

cp $CP_OPTS ${SRC}/webpage ${DEST}

mkdir -p ${DEST}/clusters
mkdir -p ${DEST}/testSuits
cp $CP_OPTS ${SRC}/clusters/*.py ${DEST}/clusters
cp $CP_OPTS ${SRC}/testSuits/*.py ${DEST}/testSuits

mkdir -p ${DEST}/lib
cp $CP_OPTS ${SRC}/lib/TestUtils.py ${DEST}/lib
cp $CP_OPTS ${SRC}/lib/SocketUtils.py ${DEST}/lib
cp $CP_OPTS ${SRC}/lib/Daemon.py ${DEST}/lib
cp $CP_OPTS ${SRC}/lib/Utils.py ${DEST}/lib
cp $CP_OPTS ${SRC}/lib/ClusterManager.py ${DEST}/lib

mkdir -p ${DEST}/rpmbuild
cp $CP_OPTS ${SRC}/rpmbuild/* ${DEST}/rpmbuild


tar -cvzf ${NAME}.tar.gz ${NAME}
rm -rf ${DEST}
