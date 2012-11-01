#!/bin/bash
exec 2>&1
set -e
set -o errtrace
set -o pipefail

function error_trap () {
    echo "script terminated with with error code $1"
}

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

trap 'e=$?; error_trap $e; exit $e' ERR

rm -f /var/lib/rpm/__db*
rpm --rebuilddb

coredump_config
