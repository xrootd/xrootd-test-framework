#!/usr/bin/env python
#-------------------------------------------------------------------------------
# Author: Lukasz Trzaska <lukasz.trzaska@cern.ch>
# Date:   22.08.2011
# File:   ClusterManager module
# Desc:   Virtual machines network manager
#-------------------------------------------------------------------------------
# Imports
#-------------------------------------------------------------------------------
from libvirt import libvirtError, VIR_ERR_NETWORK_EXIST
from string import join
import libvirt
import logging
import os
import sys
import time
import Utils
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
  <dns>
      <txt name="xrd.test" value="Welcome to xrd testing framework domain." />
      <host ip="%(xrdTestMasterIP)s">
          <hostname>master.xrd.test</hostname>
      </host>
      %(dnshostsxml)s
  </dns>
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
    xmlDnsHostPattern = """
<host ip="%(ip)s">
    <hostname>%(hostname)s</hostname>
</host>
"""
    #---------------------------------------------------------------------------
    def __init__(self):
        self.name = ""
        self.bridgeName = ""
        self.ip = ""
        self.netmask = ""
        self.DHCPRange = ("", "")   #(begin_address, end_address)
        self.DHCPHosts = []
        self.DnsHosts = []

        self.xrdTestMasterIP = ""
    #---------------------------------------------------------------------------
    def addDHCPHost(self, host):
        self.DHCPHosts.append(host)
    #---------------------------------------------------------------------------
    def addDnsHost(self, host):
        self.DnsHosts.append(host)
    #---------------------------------------------------------------------------
    @property
    def xmlDesc(self):
        hostsXML = ""
        dnsHostsXML = ""

        values = dict()
        for h in self.DHCPHosts:
            values = {"mac": h[0], "ip": h[1], "name": h[2]}
            hostsXML = hostsXML + Network.xmlHostPattern % values
            
        for dns in self.DnsHosts:
            values = {"ip": dns[0], "hostname": dns[1]}
            dnsHostsXML = dnsHostsXML + Network.xmlDnsHostPattern % values

        values = {"name": self.name,
                  "ip": self.ip, "netmask": self.netmask,
                  "bridgename": self.bridgeName,
                  "rangestart": self.DHCPRange[0], 
                  "rangeend": self.DHCPRange[1],
                  "hostsxml": hostsXML,
                  "dnshostsxml" : dnsHostsXML,
                  "xrdTestMasterIP": self.xrdTestMasterIP
                  }
        self.__xmlDesc = Network.xmlDescPattern % values
        LOGGER.debug(self.__xmlDesc)
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
      <target port='0'/>
    </console>
    <console type='pty'>
      <target type='serial' port='0'/>
    </console>
    <input type='mouse' bus='ps2'/>
    
    <graphics type='vnc' port='-1' autoport='yes' keymap='en-us'/>
    <video>
    <model type='cirrus' vram='9216' heads='1' />
    <address type='pci' domain='0x0000' bus='0x00' slot='0x02' function='0x0' />
    </video>
    
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
class Cluster(Utils.Stateful):
    #---------------------------------------------------------------------------
    S_ACTIVE        =   (10, "Cluster active")
    S_ERROR         =   (-10, "Cluster error")
    S_UNKNOWN       =   (1, "Cluster state unknown")
    S_UNKNOWN_NOHYPERV = (1, "Cluster state unknown, no hypervisor to plant it on")
    S_ACTIVE        =    (2, "Cluster active")
    '''
    Represents a cluster comprised of hosts connected through network.
    '''
    #-------------------------------------------------------------------------------
    def __init__(self):
        Utils.Stateful.__init__(self)
        self.hosts = []
        self.name = None
        self.network = None
    #---------------------------------------------------------------------------
    def addHost(self, host):
        self.hosts.append(host)
    #---------------------------------------------------------------------------
    def setEmulatorPath(self, emulator_path):
        if len(self.hosts):
            for h in self.hosts:
                h.emulatorPath = emulator_path
    #---------------------------------------------------------------------------
    def validateStatic(self):
        '''
        Check if Cluster definition is correct and sufficient
        to create a cluster.
        '''
        #check if network definition provided: whether by arguments or xmlDesc
        #@todo: validate if names, uuids and mac definitions of hosts
        # are different
        if not self.name:
            raise ClusterManagerException('Cluster definition incomplete: ' + \
                                          ' no name of cluster given')
        if not self.network or not (self.network.name and self.network.xmlDesc):
            raise ClusterManagerException('Cluster definition incomplete: ' + \
                                          ' no or wrong network definition')
    #---------------------------------------------------------------------------
    def validateDynamic(self):
        '''
        Check if Cluster definition is semantically correct e.g. if disk images
        really exists on the virtual machine it's to be planted.
        '''
        if self.hosts:
            for h in self.hosts:
                if not os.path.exists(h.diskImage):
                    return (False, "Disk image doesn't exist: " + h.diskImage)

        return (True, "")
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
    def defineHost(self, hostObj):
        '''
        Defines virtual host to cluster using given XML definition, not starting
        it.
        @param xml: libvirt XML cluster definition
        @raise ClusterManagerException: when fails
        @return: host
        '''
        host = None
        try:
            conn = self.virtConnection
            host = conn.defineXML(hostObj.xmlDesc)
        except libvirtError, e:
            try:
                host = conn.lookupByName(hostObj.name)
            except libvirtError, e:
                LOGGER.exception(e)
                msg = "Could not define host neither obtain host definition."
                raise ClusterManagerException(msg, ERR_ADD_HOST)
        return host
    #---------------------------------------------------------------------------
    def addHost(self, hostObj):
        '''
        Adds virtual host to cluster
        @param hostObj: Host object
        @raise ClusterManagerException: when fails
        @return: None
        '''
        host = None
        try:
            host = self.defineHost(hostObj)
            if not host.isActive():
                host.create()
            if not host.isActive():
                LOGGER.exception("Host created but not started.")
        except libvirtError, e:
            msg = "Could not create domain from XML: %s", e
            LOGGER.exception(msg)
            raise ClusterManagerException(msg, ERR_ADD_HOST)

        if host and host.isActive():
            LOGGER.info("Host %s created and active." % (hostObj.name))

        return host
    #---------------------------------------------------------------------------
    def defineNetwork(self, netObj):
        '''
        Defines network object without starting it.
        @param xml: libvirt XML cluster definition
        @raise ClusterManagerException: when fails
        @return: None
        '''
        net = None
        try:
            conn = self.virtConnection
            net = conn.networkDefineXML(netObj.xmlDesc)
            LOGGER.info("Defining network " + netObj.name)
        except libvirtError, e:
            LOGGER.exception(e)
            try:
                net = conn.networkLookupByName(netObj.name)
            except libvirtError, e:
                LOGGER.exception(e)
                msg = "Could not define net neither obtain net definition."
                msg += " After network already exists."
                raise ClusterManagerException(msg, ERR_CREATE_NETWORK)

        return net
    #---------------------------------------------------------------------------
    def createNetwork(self, networkObj):
        '''
        Creates and starts cluster's network. It utilizes defineNetwork
        at first and doesn't create network definition if it already exists.
        @param networkObj: Network object
        @raise ClusterManagerException: when fails
        @return: None
        '''
        net = None
        try:
            net = self.defineNetwork(networkObj)
            if not net.isActive():
                net.create()
            if not net.isActive():
                LOGGER.error("Network created but not active")
        except libvirtError, e:
            msg = "Could not define network from XML: %s", e
            LOGGER.exception(msg)
            raise ClusterManagerException(msg, ERR_CREATE_NETWORK)

        if net and net.isActive():
            LOGGER.info("Network %s created and active." % (networkObj.name))

        return net
    #---------------------------------------------------------------------------
    def createCluster(self, cluster):
        '''
        Creates whole cluster: first network, then hosts.
        @param cluster:
        '''
        self.createNetwork(cluster.network)
        if cluster.hosts and len(cluster.hosts):
            for h in cluster.hosts:
                self.addHost(h)
    #---------------------------------------------------------------------------
    def hostIsActive(self, hostObj):
        h = self.defineHost(hostObj)
        return h.isActive()
    #---------------------------------------------------------------------------
    def networkIsActive(self, netObj):
        n = self.defineNetwork(netObj)
        return n.isActive()

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
                    cl.definitionFile = modFile
                    #after load, check if cluster definition is correct
                    cl.validateStatic()
                    clusters.append(cl)
                except AttributeError, e:
                    LOGGER.exception(e)
                    raise ClusterManagerException("Method getCluster " + \
                          "can't be found in " + \
                          "file: " + str(modFile))
                except ImportError, e:
                    LOGGER.exception(e)
    return clusters
