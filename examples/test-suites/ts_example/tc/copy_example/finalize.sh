#!/bin/bash
set -e

function log () {
	echo `date +['%T']` $@
}

log "Finalizing test case on slave" @slavename@ "..."

log "Nothing to finalize."