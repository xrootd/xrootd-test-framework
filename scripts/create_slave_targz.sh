#!/bin/bash

ARCHIVE_DEST=$PWD
NAME=XrdTestSlave-0.0.1

DEST=${ARCHIVE_DEST}/${NAME}/
SRC=/home/ltrzaska/dev/pydev-workspace/xrd-test/src/
CP_OPTS=-vr

mkdir -p ${DEST}

cp $CP_OPTS ${SRC}XrdTestSlave.py ${DEST}
cp $CP_OPTS ${SRC}XrdTestSlave.conf ${DEST}
cp $CP_OPTS ${SRC}certs/slave/slavecert.pem ${DEST}
cp $CP_OPTS ${SRC}certs/slave/slavekey.pem ${DEST}

mkdir -p ${DEST}lib/
cp $CP_OPTS ${SRC}lib/TestUtils.py ${DEST}lib
cp $CP_OPTS ${SRC}lib/SocketUtils.py ${DEST}lib
cp $CP_OPTS ${SRC}lib/Daemon.py ${DEST}lib
cp $CP_OPTS ${SRC}lib/Utils.py ${DEST}lib

tar -cvzf ${NAME}.tar.gz ${NAME}
rm -rf ${DEST}
