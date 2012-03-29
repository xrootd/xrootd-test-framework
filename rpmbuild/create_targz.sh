#!/bin/bash

if [ -z "$1" ]; then
        echo "CORRECT usage is:"
	echo "create_targz.sh SRC_PATH"
	exit 0
fi
echo "STARTING COPYING FILES FROM $1"

ARCHIVE_DEST=$PWD
NAME=xrdtest-0.0.1

DEST=${ARCHIVE_DEST}/${NAME}
SRC=$1
CP_OPTS=-r

set -e

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

cp -r $CP_OPTS ${SRC}/webpage ${DEST}

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
cp $CP_OPTS ${SRC}/lib/ClusterUtils.py ${DEST}/lib

mkdir -p ${DEST}/rpmbuild
cp $CP_OPTS ${SRC}/rpmbuild/*.sh ${DEST}/rpmbuild
cp $CP_OPTS ${SRC}/rpmbuild/xrdtest*d ${DEST}/rpmbuild
cp $CP_OPTS ${SRC}/rpmbuild/*.spec ${DEST}/rpmbuild

tar -cvzf ${NAME}.tar.gz ${NAME}
rm -rf ${DEST}
