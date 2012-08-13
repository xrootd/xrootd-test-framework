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

	if [ ! -d /mnt ]; then
		mkdir /mnt
	fi

	if [ ! -d /mnt/xrootd ]; then
		mkdir /mnt/xrootd
	fi
	
	# if ! grep -Fxq "xrootdfs" /etc/fstab
	# then
    	# echo "xrootdfs  /mnt/xrootd  fuse  rdr=xroot://metamanager1.xrd.test:1094//data/,uid=xrootd,nosuid,nodev,allow_other 0 0" >> /etc/fstab
		# mount /mnt/xrootd
	# fi
	
	service cmsd stop
	service xrootd stop
	
	mount -t fuse xrootdfs /mnt/xrootd -o rdr=xroot://metamanager1.xrd.test:1094//data,uid=daemon,nosuid,nodev,allow_other

else
	log "Nothing to initialize." 
fi
