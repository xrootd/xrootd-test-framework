#!/bin/bash

if [ -z "$1" ]; then
  echo "usage: build_src_tarball.sh <src_path>"
  exit 0
fi
echo "Copying files from $1"

VERSION=0.1
NAME=xrdtest-$VERSION

ARCHIVE_DEST=$PWD
DEST=$ARCHIVE_DEST/$NAME
SRC=$1

set -e

mkdir -p $DEST/src
mkdir -p $DEST/src/XrdTest
mkdir -p $DEST/src/conf
mkdir -p $DEST/src/webpage
mkdir -p $DEST/examples/clusters
mkdir -p $DEST/examples/test-suites
mkdir -p $DEST/packaging
mkdir -p $DEST/packaging/rpm
mkdir -p $DEST/docs
mkdir -p $DEST/utils

for n in Slave Master Hypervisor; do
  cp -R $SRC/src/XrdTest$n.py $DEST/src
  cp -R $SRC/src/conf/XrdTest$n.conf $DEST/src/conf
done

cp -R $SRC/src/webpage $DEST/src
cp -R $SRC/docs $DEST
cp -R $SRC/utils $DEST

cp -R $SRC/examples/clusters/ $DEST/examples/clusters
cp -R $SRC/examples/test-suites/ $DEST/examples/test-suites

cp -R $SRC/src/XrdTest/ $DEST/src

cp -R $SRC/packaging/rpm/xrdtest-*.init $DEST/packaging/rpm

tar -cvzf $NAME.tar.gz $NAME
rm -rf $DEST