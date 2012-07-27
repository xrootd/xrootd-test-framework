#!/bin/bash

HOSTNAME=`hostname`
echo -ne `date` $HOSTNAME "Running test case\n"

cd /tmp

#------------------------------------------------------------------------------- 

if [ $HOSTNAME == "client1" ]; then
  
  rm testreceive
  xrdcp xroot://metamanager1.xrd.test:1094//tmp/testfile testreceive
  ls -al

#------------------------------------------------------------------------------- 

else
  echo "nothing to do this time" 
fi

