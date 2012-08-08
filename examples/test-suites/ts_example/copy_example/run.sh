#!/bin/bash
set -e

function log () {
	echo `date +['%T']` $@
}

log "Running test case on slave" @slavename@ "..."

if [[ @slavename@ =~ client ]]; then
  
	cd /data
	py.test

else
	log "Nothing to do this time." 
fi

