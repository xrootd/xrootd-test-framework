#!/bin/bash
set -e

function log () {
	echo `date +['%T']` $@
}

log "Initializing test case on slave" @slavename@ "..."

cd /data

if [[ @slavename@ =~ ds ]]; then
  
	if [ -f testfile ]; then
		rm testfile
	fi
	
	truncate --size=50M testfile
	chown daemon.daemon testfile

elif [[ @slavename@ =~ client ]]; then
	
	log "Mounting xrootd fuse on @slavename@ ..."
	
	# mount -t fuse xrootdfs /xrootdfs -o rdr=xroot://metamanager1.xrd.test:1094//data,uid=daemon

	if [ ! -d /mnt ]; then
		mkdir /mnt
	fi

	if [ ! -d /mnt/xrootd ]; then
		mkdir /mnt/xrootd
	fi
	
	if ! grep -Fxq "xrootdfs" /etc/fstab
	then
    	echo "xrootdfs  /mnt/xrootd  fuse  rdr=xroot://metamanager1.xrd.test:1094//data/,uid=xrootd 0 0" >> /etc/fstab
		mount /mnt/xrootd
	fi
	

else
	log "Nothing to initialize." 
fi
