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

else
    log "Nothing to initialize." 
fi
