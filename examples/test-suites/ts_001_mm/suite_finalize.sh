#!/bin/bash
set -e

function log () {
    echo `date +['%T']` $@
}

log "Finalizing test suite on slave" @slavename@ "..."

log "Nothing to finalize."
