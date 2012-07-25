#!/bin/bash
echo -ne `date` @slavename@ "Initializing test case\n"

CONFIG_FILE=xrd_cluster_002_test.cf
CONFIG_PATH=/etc/xrootd/${CONFIG_FILE}

mkdir -p tmp_inittest
rm -rf tmp_inittest/*
cd tmp_inittest

echo "#----------------------------------------------"
echo "# DOWNLOADING XROOTD CONFIG FILE ${CONFIG_FILE}"
wget "http://master.xrd.test:8080/downloadScript/clusters/${CONFIG_FILE}" -O $CONFIG_FILE
mv $CONFIG_FILE $CONFIG_PATH

# extracting machine name from hostname
arr=($(echo @slavename@ | tr "." " "))
NAME=${arr[0]}

echo "#----------------------------------------------"
echo "# CREATING SERVICE CONFIG FILE etc/sysconfig/xrootd"

SERVICE_CONFIG_FILE=/etc/sysconfig/xrootd
rm -rf $SERVICE_CONFIG_FILE
touch $SERVICE_CONFIG_FILE
UCASE_NAME=$(echo $NAME | tr a-z A-Z)
echo "
XROOTD_USER=daemon
XROOTD_GROUP=daemon
XROOTD_${UCASE_NAME}_OPTIONS=\" -l /var/log/xrootd/xrootd.log -c ${CONFIG_PATH} -k 7\"
CMSD_${UCASE_NAME}_OPTIONS=\" -l /var/log/xrootd/cmsd.log -c ${CONFIG_PATH} -k 7\"
XROOTD_INSTANCES=\"${NAME}\"
CMSD_INSTANCES=\"${NAME}\"
" > $SERVICE_CONFIG_FILE
echo "#----------------------------------------------"
echo "CONTENT:"
cat $SERVICE_CONFIG_FILE

echo "#----------------------------------------------"
echo "# STARTING XROOTD AND CMSD FOR MACHINE $NAME"
echo "# CONFIG FILE $CONFIG_PATH"

mkdir -p /var/log/xrootd
mkdir -p /root/xrdfilesystem
df -ah

service xrootd setup
service xrootd start
service cmsd start

echo "#----------------------------------------------"
echo "xrootd /var/log/xrootd/${NAME}/xrootd.log file"
cat /var/log/xrootd/${NAME}/xrootd.log
echo "#----------------------------------------------"
echo "cmsd /var/log/xrootd/${NAME}/cmsd.log file"
cat /var/log/xrootd/${NAME}/cmsd.log
echo "#----------------------------------------------"

cd /tmp
su - xroot
#sleep 2m

#------------------------------------------------------------------------------- 

if [ $HOSTNAME == "ds1" ]; then
  
  rm testfile
  truncate --size=50M testfile
  ls -al
  
#------------------------------------------------------------------------------- 

elif [ $HOSTNAME == "ds2" ]; then
  
  rm testfile
  truncate --size=50M testfile
  ls -al

#------------------------------------------------------------------------------- 

elif [ $HOSTNAME == "ds3" ]; then
  
  rm testfile
  truncate --size=50M testfile
  ls -al

#------------------------------------------------------------------------------- 

elif [ $HOSTNAME == "ds4" ]; then
  
  rm testfile
  truncate --size=50M testfile
  ls -al

#------------------------------------------------------------------------------- 

else
  echo "nothing left to init" 
fi
