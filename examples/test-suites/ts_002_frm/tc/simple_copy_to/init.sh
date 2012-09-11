#!/bin/bash
set -e

function log () {
    echo `date +['%T']` $@
}

log "Initializing test case on slave" @slavename@ "..."
    
cd /data

if [[ @slavename@ =~ client ]]; then
  
    if [ -f testfile ]; then
        rm testfile
    fi
    
    truncate --size=100M testfile
    chown daemon.daemon testfile
    ls -al
  
elif [[ @slavename@ =~ ds ]]; then
  
    if [ -f testfile_from_client ]; then
        rm testfile_from_client
    fi
  
else
    log "Nothing to initialize." 
fi
