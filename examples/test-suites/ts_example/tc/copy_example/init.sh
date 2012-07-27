#!/bin/bash
echo -ne `date` @slavename@ "Initializing test case\n"

CLUSTER_NAME=cluster_example
CONFIG_FILE=xrd_cluster_example.cf
CONFIG_PATH=/etc/xrootd/${CONFIG_FILE}

mkdir -p tmp_inittest
rm -rf tmp_inittest/*
cd tmp_inittest

echo "#-------------------------------------------------------------------------"
echo "# Downloading xrootd config file ${CONFIG_FILE}"
rm $CONFIG_PATH
wget "http://master.xrd.test:8080/downloadScript/clusters/${CLUSTER_NAME}/${CONFIG_FILE}" -O $CONFIG_FILE
mv $CONFIG_FILE $CONFIG_PATH

# extracting machine name from hostname
arr=($(echo @slavename@ | tr "." " "))
NAME=${arr[0]}

echo "#-------------------------------------------------------------------------"
echo "# Creating service config file etc/sysconfig/xrootd:"

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
FRMD_INSTANCES=\"${NAME}\"
" > $SERVICE_CONFIG_FILE

cat $SERVICE_CONFIG_FILE

echo "#-------------------------------------------------------------------------"
echo "# Starting xrootd and cmsd for machine $NAME"
echo "# Config file: $CONFIG_PATH"

mkdir -p /var/log/xrootd
mkdir -p /root/xrdfilesystem

service xrootd setup
service xrootd start
service cmsd start

echo "#-------------------------------------------------------------------------"
echo "xrootd /var/log/xrootd/${NAME}/xrootd.log file:"
tail --lines=100 /var/log/xrootd/${NAME}/xrootd.log
echo "#-------------------------------------------------------------------------"
echo "cmsd /var/log/xrootd/${NAME}/cmsd.log file:"
tail --lines=100 /var/log/xrootd/${NAME}/cmsd.log
echo "#-------------------------------------------------------------------------"

cd /tmp

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
