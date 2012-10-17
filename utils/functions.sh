#!/bin/bash
exec 2>&1
trap 'previous_command=$this_command; this_command=$BASH_COMMAND' DEBUG
trap 'e=$?; echo "command [ $previous_command ] failed with error code $e"; exit $e' ERR

function log () {
    echo `date +['%T']` $@
}

function stamp () {
    $@ | perl -p -MPOSIX -e 'BEGIN {$!=1} $_ = strftime("[%T]", localtime) . "\t" . $_'
}

function assert_fail () {
    if "$@"; then 
        log "$* didn't fail."
        exit 1
    else
        log "$* failed as expected."
    fi
}
