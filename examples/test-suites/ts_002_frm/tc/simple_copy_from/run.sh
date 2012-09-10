#!/bin/bash
set -e

function log () {
	echo `date +['%T']` $@
}

log "Running test case on slave" @slavename@ "..."

cd /data

if [ @slavename@ == "client1" ]; then

	if [ -f testreceive ]; then
		rm testreceive
	fi
	
	xrdcp xroot://frm1.xrd.test:1094//data/testfile testreceive

else
	log "Nothing to do this time." 
fi

