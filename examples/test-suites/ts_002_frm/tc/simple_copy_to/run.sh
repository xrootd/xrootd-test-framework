#!/bin/bash
set -e

function log () {
	echo `date +['%T']` $@
}

log "Running test case on slave" @slavename@ "..."

cd /data

if [[ @slavename@ =~ "client" ]]; then
  
	xrdcp testfile xroot://frm1.xrd.test:1094//data/testfile_from_client

else
	log "Nothing to do this time." 
fi

