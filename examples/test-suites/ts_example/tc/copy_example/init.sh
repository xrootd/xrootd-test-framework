#!/bin/bash
echo -ne `date` @slavename@ "Initializing test case ...\n\n"

cd /data

if [[ @slavename@ =~ ds ]]; then
  
  rm testfile
  truncate --size=50M testfile
  chown daemon.daemon testfile
  ls -al

else
  echo "Nothing to initialize." 
fi
