#!/bin/bash
set -e

function log () {
    echo `date +['%T']` $@
}

function stamp () {
    $@ | perl -p -MPOSIX -e 'BEGIN {$!=1} $_ = strftime("[%T]", localtime) . "\t" . $_'
}

log "Finalizing test case on slave" @slavename@ "..."
    
if [[ @slavename@ =~ ds  ]]; then
  
    stamp ls -al /data

else
    log "Nothing to finalize." 
fi

