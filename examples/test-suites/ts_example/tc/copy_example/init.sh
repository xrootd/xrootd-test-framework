#!/bin/bash
echo -ne `date` @slavename@ "Initializing test case\n"

cd /tmp

if [[ @slavename@ =~ ds ]]; then
  
  rm testfile
  truncate --size=50M testfile
  ls -al

else
  echo "Nothing to initialize." 
fi
