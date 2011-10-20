#!/usr/bin/env python
#-------------------------------------------------------------------------------
# Author: Lukasz Trzaska <lukasz.trzaska@cern.ch>
# Date:   22.08.2011
# File:   ClusterManager module
# Desc:   Virtual machines network manager
#-------------------------------------------------------------------------------
# Imports
#-------------------------------------------------------------------------------
from libvirt import libvirtError
from string import join
import libvirt
import logging
import os
import sys
#-------------------------------------------------------------------------------
# Global variables
#-------------------------------------------------------------------------------
logging.basicConfig(format='%(levelname)s line %(lineno)d: %(message)s', \
                    level=logging.INFO)
LOGGER = logging.getLogger(__name__)
LOGGER.debug("Running script: " + __file__)
#-------------------------------------------------------------------------------
# Global error types
#-------------------------------------------------------------------------------
ERR_UNKNOWN = 1
ERR_CONNECTION = 2
ERR_ADD_HOST = 4
ERR_CREATE_NETWORK = 8
#-------------------------------------------------------------------------------
class ClusterManagerException(Exception):
    '''
    General Exception raised by module
    '''
    #---------------------------------------------------------------------------
    def __init__(self, desc, typeFlag=ERR_UNKNOWN):
        '''
        Constructs Exception
        @param desc: description of an error
        @param typeFlag: represents type of an error, taken from class constants
        '''
        self.desc = desc
        self.type = typeFlag
    #---------------------------------------------------------------------------
    def __str__(self):
        '''
        Returns textual representation of an error
        '''
        return repr(self.desc)
#-------------------------------------------------------------------------------
def getFileContent(filePath):
    '''
    Read and return whole file content as a string
    @param filePath:
    '''
    fd = open(filePath, "r")
    lines = fd.readlines()
    fd.close()

    xmlDesc = join(lines)
    if len(xmlDesc) <= 0:
        logging.info("File %s is empty.", file)

    return xmlDesc
#-------------------------------------------------------------------------------
class Network(object):
    '''
    Represents a virtual network
    '''
# XML pattern representing XML configuration of libvirt network
    xmlDescPattern = """
<network>
  <name>%(name)s</name>
  <bridge name="%(bridgename)s" />
  <forward/>
  <ip address="%(ip)s" netmask="%(netmask)s">
    <dhcp>
      <range start="%(rangestart)s" end="%(rangeend)s" />
    %(hostsxml)s
    </dhcp>
  </ip>
</network>
"""
    xmlHostPattern = """
<host mac="%(mac)s" name="%(name)s" ip="%(ip)s" />
"""
    #---------------------------------------------------------------------------
    def __init__(self):
        self.name = ""
        self.bridgeName = ""
        self.ip = ""
        self.netmask = ""
        self.DHCPRange = ("", "")   #(begin_address, end_address)
        self.DHCPHosts = []
    #---------------------------------------------------------------------------
    def addDHCPHost(self, host):
        self.DHCPHosts.append(host)
    #---------------------------------------------------------------------------
    @property
    def xmlDesc(self):
        hostsXML = ""

        values = dict()
        for h in self.DHCPHosts:
            values = {"mac": h[0], "ip": h[1], "name": h[2]}
            hostsXML = hostsXML + Network.xmlHostPattern % values

        values = {"name": self.name,
                  "ip": self.ip, "netmask": self.netmask,
                  "bridgename": self.bridgeName,
                  "rangestart": self.DHCPRange[0], 
                  "rangeend": self.DHCPRange[1],
                  "hostsxml": hostsXML
                  }
        self.__xmlDesc = Network.xmlDescPattern % values
        return self.__xmlDesc
#-------------------------------------------------------------------------------
class Host(object):
    '''
    Represents a virtual host which may be added to network
    '''
# XML pattern representing XML configuration of libvirt domain
    xmlDomainPattern = """
<domain type='kvm'>
  <name>%(name)s</name>
  <uuid>%(uuid)s</uuid>
  <memory>%(ramSize)s</memory>
  <vcpu>1</vcpu>
  <os>
    <type arch='%(arch)s' machine='pc'>hvm</type>
    <boot dev='hd'/>
  </os>
  <features>
    <acpi/>
    <apic/>
    <pae/>
  </features>
  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>restart</on_crash>
  <devices>
    <emulator>%(emulatorPath)s</emulator>
    <disk type='file' device='disk'>
      <driver name='qemu' type='raw'/>
      <source file='%(diskImage)s'/>
      <target dev='hda' bus='ide'/>
      <address type='drive' controller='0' bus='0' unit='0'/>
    </disk>
    <disk type='block' device='cdrom'>
      <driver name='qemu' type='raw'/>
      <target dev='hdc' bus='ide'/>
      <readonly/>
      <address type='drive' controller='0' bus='1' unit='0'/>
    </disk>
    <controller type='ide' index='0'>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x01' 
      function='0x1'/>
    </controller>
    <interface type='network'>
      <mac address='%(macAddress)s'/>
      <source network='%(sourceNetwork)s'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x03' 
      function='0x0'/>
    </interface>
    <console type='pty'>
      <target type='serial' port='0'/>
    </console>
    <input type='mouse' bus='ps2'/>
    <memballoon model='virtio'>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x04' 
      function='0x0'/>
    </memballoon>
  </devices>
</domain>
"""
    #---------------------------------------------------------------------------
    def __init__(self):
        self.uuid = ""
        self.name = ""
        self.diskImage = ""
        self.ramSize = ""
        self.macAddress = ""
        self.arch = ""
        self.sourceNetwork = ""
        self.emulatorPath = "/usr/libexec/qemu-kvm"
        self.__xmlDesc = ""
    #---------------------------------------------------------------------------
    @property
    def xmlDesc(self):
        values = self.__dict__
        self.__xmlDesc = self.xmlDomainPattern % values

        return self.__xmlDesc
#-------------------------------------------------------------------------------
class Cluster(object):
    '''
    Represents a cluster comprised of hosts connected through network.
    '''
    #-------------------------------------------------------------------------------
    def __init__(self):
        self.hosts = []
        self.name = None
        self.network = None
    #---------------------------------------------------------------------------
    def addHost(self, host):
        self.hosts.append(host)
        #---------------------------------------------------------------------------
    def validate(self):
        '''
        Check if Cluster definition is correct and sufficient
        to create a cluster.
        '''
        #check if network definition provided: whether by arguments or xmlDesc
        #@todo: validate if names, uuids and mac definitions of hosts
        # are different
        if not self.network or not (self.network.name and self.network.xmlDesc):
            raise ClusterManagerException('Cluster definition incomplete: ' + \
                                          ' no or wrong network definition')
#-------------------------------------------------------------------------------
class ClusterManager:
    '''
    Virtual machines cluster's manager
    '''
    #---------------------------------------------------------------------------
    def __init__(self):
        '''
        Creates Manager instance. Needs url to virtual virt domains manager
        '''
        # holds libvirt connection of a type libvirt.virConnect
        self.virtConnection = None
    #---------------------------------------------------------------------------
    def connect(self, url="qemu:///system"):
        '''
        Creates and returns connection to virtual machines manager
        @param url: connection url
        @raise ClusterManagerException: when fails to connect
        @return: None
        '''
        try:
            self.virtConnection = libvirt.open(url)
        except libvirtError, e:
            msg = "Could not create connection to libvirt: %s", e
            LOGGER.error(msg)
            raise ClusterManagerException(msg, ERR_CONNECTION)
        else:
            LOGGER.debug("Connected to libvirt manager.")
    #---------------------------------------------------------------------------
    def disconnect(self):
        '''
        Disconnects from libvirt manager
        @raise ClusterManagerException: when fails
        '''
        try:
            self.virtConnection.close()
        except libvirtError, e:
            msg = "Could not disconnect from libvirt: %s", e
            LOGGER.error(msg)
            raise ClusterManagerException(msg, ERR_CONNECTION)
        else:
            LOGGER.debug("libvirt manager disconnected")
    #---------------------------------------------------------------------------
    def addHostXml(self, xmlDesc):
        '''
        Adds virtual host to cluster using given XML definition
        @param xml: libvirt XML cluster definition
        @raise ClusterManagerException: when fails
        @return: None
        '''
        try:
            conn = self.virtConnection
            conn.createXML(xmlDesc, libvirt.VIR_DOMAIN_NONE)
        except libvirtError, e:
            msg = "Could not create domain from XML: %s", e
            LOGGER.exception(msg)
            raise ClusterManagerException(msg, ERR_ADD_HOST)
        else:
            LOGGER.info("Domain created.")
    #---------------------------------------------------------------------------
    def addHost(self, hostObj):
        '''
        Adds virtual host to cluster
        @param hostObj: Host object
        @raise ClusterManagerException: when fails
        @return: None
        '''
        self.addHostXml(hostObj.xmlDesc)
    #---------------------------------------------------------------------------
    def createNetworkXml(self, xmlDesc):
        '''
        Creates and starts virtual network using given XML definition
        @param xmlDesc: libvirt XML network definition
        @raise ClusterManagerException: when fails
        @return: None
        '''
        try:
            conn = self.virtConnection
            net = conn.networkCreateXML(xmlDesc)
            if not net.isActive:
                LOGGER.error("Network created but not active")
        except libvirtError, e:
            msg = "Could not define network from XML: %s", e
            LOGGER.exception(msg)
            raise ClusterManagerException(msg, ERR_CREATE_NETWORK)
        else:
            LOGGER.info("Network created and active.")
    #---------------------------------------------------------------------------
    def createNetwork(self, networkObj):
        '''
        Creates and starts cluster's network
        @param networkObj: Network object
        @raise ClusterManagerException: when fails
        @return: None
        '''
        self.createNetworkXml(networkObj.xmlDesc)

#---------------------------------------------------------------------------
def loadClustersDefs(path):
    '''
    Loads cluster definitions from .py files stored in path directory
    @param path: path for .py files, storing cluster definitions
    '''
    global LOGGER

    clusters = []
    if os.path.exists(path):
        for f in os.listdir(path):
            fp = path + os.sep + f
            (modPath, modFile) = os.path.split(fp)
            modPath = os.path.abspath(modPath)
            (modName, ext) = os.path.splitext(modFile)

            if os.path.isfile(fp) and ext == '.py':
                mod = None
                cl = None
                try:
                    if not modPath in sys.path:
                        sys.path.insert(0, modPath)

                    mod = __import__(modName, {}, {}, ['getCluster'])
                    cl = mod.getCluster()
                    cl.name = modFile
                    #after load, check if cluster definition is correct
                    cl.validate()
                    clusters.append(cl)
                except AttributeError:
                    LOGGER.exception()
                    raise ClusterManagerException("Method getCluster " + \
                          "can't be found in " + \
                          "file: " + str(modFile))
                except ImportError:
                    LOGGER.exception()
    return clusters
