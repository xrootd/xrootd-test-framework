#!/bin/bash
exec 2>&1
trap 'previous_command=$this_command; this_command=$BASH_COMMAND' DEBUG
trap 'e=$?; echo "command [ $previous_command ] failed with error code $e"; exit $e' ERR

function coredump_config () {
    # Make sure corefiles are enabled and gdb is installed
    yum -y -q install gdb > /dev/null
    
    if ! grep -q "kernel.core_pattern" /etc/sysctl.conf; then
        echo "kernel.core_pattern=/tmp/cores/core.%h.%p.%t" >> /etc/sysctl.conf
    fi

    mkdir -p /tmp/cores; chmod a+rwx /tmp/cores
    ulimit -c unlimited
}

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

coredump_config
