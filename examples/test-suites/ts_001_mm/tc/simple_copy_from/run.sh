#!/bin/bash
set -e

function log () {
    echo `date +['%T']` $@
}

function stamp () {
    $@ | perl -p -MPOSIX -e 'BEGIN {$!=1} $_ = strftime("[%T]", localtime) . "\t" . $_'
}

log "Running test case on slave" @slavename@ "..."

cd /data

if [ @slavename@ == "client1" ]; then
    
    if [ -f testreceive ]; then
        rm testreceive
    fi
    
    xrdcp xroot://metamanager1.xrd.test:1094//data/testfile testreceive

else
    log "Nothing to do this time." 
fi

