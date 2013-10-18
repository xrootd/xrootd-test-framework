#!/bin/bash

#-------------------------------------------------------------------------------
# Set up the output streams and core directories
#-------------------------------------------------------------------------------
exec 2>&1

yum -y -q install gdb > /dev/null
    
if ! grep -q "kernel.core_pattern" /etc/sysctl.conf; then
   echo "kernel.core_pattern=/tmp/cores/core.%h.%p.%t" >> /etc/sysctl.conf
fi

mkdir -p /tmp/cores; chmod a+rwx /tmp/cores
ulimit -c unlimited

#-------------------------------------------------------------------------------
# Logging
#-------------------------------------------------------------------------------
function log()
{
  echo `date +"[%F %T]"` "$@"
}

#-------------------------------------------------------------------------------
# Run a command display it if failed and exit the script
#-------------------------------------------------------------------------------
function run()
{
  if [ $# -lt 1 ]; then
    echo "[!] Run function requires the command"
    exit 1
  fi

  OUTPUT=`eval $@ 2>&1`
  if [ $? -ne 0 ]; then
    log "[$@]: $OUTPUT"
    exit 1
  fi
}
