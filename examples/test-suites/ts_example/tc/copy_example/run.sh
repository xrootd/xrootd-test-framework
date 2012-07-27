#!/bin/bash
echo -ne `date` @slavename@ "Running test case\n\n"

cd /tmp

if [ @slavename@ == "client1" ]; then
  
  rm testreceive
  xrdcp xroot://metamanager1.xrd.test:1094//tmp/testfile testreceive
  ls -al

else
  echo "nothing to do this time" 
fi
