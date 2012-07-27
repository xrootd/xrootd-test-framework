#!/bin/bash
echo -ne `date` @slavename@ "Initializing test suite ...\n\n"

#---------------------------------------------------------------------------------------------------------
# Important parameters

CLUSTER_NAME=cluster_example
CONFIG_FILE=xrd_cluster_example.cf
CONFIG_PATH=/etc/xrootd/${CONFIG_FILE}
#---------------------------------------------------------------------------------------------------------

function hr {
	echo -n "#"; for i in {1..150}; do echo -ne "-"; done; echo -e
}

function section () {
	hr; echo $@; hr
}

#---------------------------------------------------------------------------------------------------------
section "# Fetching latest xrootd build ..."

mkdir -p tmp_initsh
rm -rf tmpinitsh/*
cd tmp_initsh
wget "http://master.xrd.test:8080/showScript/lib/get_xrd_latest.py" -O get_xrd_latest.py
chmod 755 get_xrd_latest.py
rm -rf xrd_rpms
python get_xrd_latest.py
rm -rf xrd_rpms/slc-6-x86_64/xrootd-*.src.*.rpm
rm -rf xrd_rpms/slc-6-x86_64/xrootd-*-devel-*.rpm

#---------------------------------------------------------------------------------------------------------
section "# Installing xrootd packages ..."

rpm -iv --force xrd_rpms/slc-6-x86_64/xrootd-libs-*.rpm
rpm -iv --force xrd_rpms/slc-6-x86_64/xrootd-client-*.rpm
rpm -iv --force xrd_rpms/slc-6-x86_64/xrootd-client-admin-perl-*.rpm
rpm -iv --force xrd_rpms/slc-6-x86_64/xrootd-fuse-*.rpm
rpm -iv --force xrd_rpms/slc-6-x86_64/xrootd-server-*.rpm
cd ..

#---------------------------------------------------------------------------------------------------------
section "# Downloading xrootd config file ${CONFIG_FILE}"

mkdir -p tmp_inittest
rm -rf tmp_inittest/*
cd tmp_inittest

rm $CONFIG_PATH
wget "http://master.xrd.test:8080/downloadScript/clusters/${CLUSTER_NAME}/${CONFIG_FILE}" -O $CONFIG_FILE
mv $CONFIG_FILE $CONFIG_PATH

cat $CONFIG_PATH
# extracting machine name from hostname
arr=($(echo @slavename@ | tr "." " "))
NAME=${arr[0]}

#---------------------------------------------------------------------------------------------------------
section "# Creating service config file etc/sysconfig/xrootd ..."

SERVICE_CONFIG_FILE=/etc/sysconfig/xrootd
rm -rf $SERVICE_CONFIG_FILE
touch $SERVICE_CONFIG_FILE
UCASE_NAME=$(echo $NAME | tr a-z A-Z)

echo "
XROOTD_USER=daemon
XROOTD_GROUP=daemon

XROOTD_${UCASE_NAME}_OPTIONS=\" -l /var/log/xrootd/xrootd.log -c ${CONFIG_PATH} -k 7\"
CMSD_${UCASE_NAME}_OPTIONS=\" -l /var/log/xrootd/cmsd.log -c ${CONFIG_PATH} -k 7\"
PURD_${UCASE_NAME}_OPTIONS=\" -l /var/log/xrootd/purged.log -c ${CONFIG_PATH} -k 7\"
XFRD_${UCASE_NAME}_OPTIONS=\" -l /var/log/xrootd/xfrd.log -c ${CONFIG_PATH} -k 7\"

XROOTD_INSTANCES=\"${NAME}\"
CMSD_INSTANCES=\"${NAME}\"
PURD_INSTANCES=\"${NAME}\"
XFRD_INSTANCES=\"${NAME}\"
" > $SERVICE_CONFIG_FILE

#---------------------------------------------------------------------------------------------------------
section "# Starting xrootd and cmsd for machine $NAME"

echo "Config file: $CONFIG_PATH"
mkdir -p /var/log/xrootd
mkdir -p /root/xrdfilesystem

service xrootd setup
service xrootd start
service cmsd start

#---------------------------------------------------------------------------------------------------------
section "# xrootd /var/log/xrootd/${NAME}/xrootd.log file:"
tail --lines=100 /var/log/xrootd/${NAME}/xrootd.log

#---------------------------------------------------------------------------------------------------------
section "# cmsd /var/log/xrootd/${NAME}/cmsd.log file:"
tail --lines=100 /var/log/xrootd/${NAME}/cmsd.log

section "# Suite initialization complete."
