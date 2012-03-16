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
import Utils
import libvirt
import logging
import os
import sys
from tempfile import NamedTemporaryFile
from copy import copy
import threading
from Utils import SafeCounter
import uuid
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
ERR_UNKNOWN         = 1
ERR_CONNECTION      = 2
ERR_ADD_HOST        = 4
ERR_CREATE_NETWORK  = 8
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
        logging.info("File %s is empty." % file)

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

        #fields beneath filled automatically by hypervisor
        self.xrdTestMasterIP = ""
    #---------------------------------------------------------------------------
    def addDnsHost(self, host):
        self.DnsHosts.append(host)
    #---------------------------------------------------------------------------
    def addDHCPHost(self, host):
        self.DHCPHosts.append(host)
    #---------------------------------------------------------------------------
    def addHost(self, host):
        '''
        Add host to network. First to DHCP and then to DNS.
        @param host: tuple (MAC address, IP address, HOST fqdn)
        '''
        self.addDHCPHost(host)
        self.addDnsHost((host[1], host[2]))
    #---------------------------------------------------------------------------
    def addHosts(self, hostsList):
        '''
        Add hosts to network.
        @param param: hostsList
        '''
        for h in hostsList:
            self.addHost(h)
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
      <source file='%(runningDiskImage)s'/>
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
    <!-- VIDEO SECTION - NORMALLY NOT NEEDED
    <graphics type='vnc' port='-1' autoport='yes' keymap='en-us'/>
    <video>
    <model type='cirrus' vram='9216' heads='1' />
    <address type='pci' domain='0x0000' bus='0x00' slot='0x02' function='0x0' />
    </video>
    END OF VIDEO SECTION -->
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
        self.diskImage = None
        self.runningDiskImage = ""
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
    S_ACTIVE = (10, "Cluster active")
    S_ERROR = (-10, "Cluster error")
    S_UNKNOWN = (1, "Cluster state unknown")
    S_UNKNOWN_NOHYPERV = (1, "Cluster state unknown, no hypervisor to plant it on")
    S_DEFINITION_SENT = (2, "Cluster definition sent do hypervisor to start")
    S_ACTIVE = (2, "Cluster active")
    S_STOPPED = (3, "Cluster stopped")
    S_STOPCOMMAND_SENT = (4, "Cluster stop command sent to cluster")
    '''
    Represents a cluster comprised of hosts connected through network.
    '''
    #-------------------------------------------------------------------------------
    def __init__(self):
        Utils.Stateful.__init__(self)
        self.hosts = []
        self.name = None
        self.info = None
        self.network = None

        self.defaultHost = Host()
        self.defaultHost.diskImage = '/data/virtual/images/lt_slc5_refslave.img'
        self.defaultHost.arch = 'x86_64'
        self.defaultHost.ramSize = '524288'
        self.defaultHost.sourceNetwork = None
    #---------------------------------------------------------------------------
    def addHost(self, host):
        if not hasattr(host, "diskImage") or not host.diskImage:
            host.diskImage = self.defaultHost.diskImage
        if not hasattr(host, "arch") or not host.arch:
            host.arch = self.defaultHost.arch
        if not hasattr(host, "ramSize") or not host.ramSize:
            host.ramSize = self.defaultHost.ramSize
        if not hasattr(host, "sourceNetwork") or not host.sourceNetwork:
            host.sourceNetwork = self.defaultHost.sourceNetwork
        if not host.diskImage:
            raise ClusterManagerException(('Host %s definition has no ' + \
                                          'disk image defined') % host.name)

        self.hosts.append(host)
    #---------------------------------------------------------------------------
    def addHosts(self, hosts):
        for h in hosts:
            self.addHosts(h)
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

        umacs = []
        uips = []
        for h in self.hosts:
            if h.macAddress in umacs:
                raise ClusterManagerException(('Host MAC %s address ' + \
                                               'doubled') % h.macAddress)
            umacs.append(h.macAddress)

        if self.network.ip == self.network.DHCPRange[0]:
            raise ClusterManagerException(('Network %s [%s] IP the ' + \
                                           'same as DHCPRange ' + \
                                           ' first address') \
                                          % (self.network.name, \
                                             self.definitionFile))
    #---------------------------------------------------------------------------
    def validateDynamic(self):
        '''
        Check if Cluster definition is semantically correct i.e. on the 
        hypervisor's machine e.g. if disk images really exists on 
        the machine it's to be planted.
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
                                #used only if orinal machine is to
                                #to be reconfigured, instance is run from 
                                #original image and it's not deleted after
    #---------------------------------------------------------------------------
    def __init__(self):
        '''
        Creates Manager instance. Needs url to virtual virt domains manager
        '''
        # holds libvirt connection of a type libvirt.virConnect
        self.virtConnection = None
        #dictionary of currently running hosts
        self.hosts = {}
        self.nets = {}

        self.tmpImagesDir = "/tmp"
        self.tmpImagesPrefix = "tmpxrdim_"
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
            msg = "Could not create connection to libvirt: %s" % e
            LOGGER.error(msg)
            raise ClusterManagerException(msg, ERR_CONNECTION)
        else:
            LOGGER.debug("Connected to libvirt manager.")

    #---------------------------------------------------------------------------
    def disconnect(self):
        '''
        Undefines and removes all virtual machines and networks and
        disconnects from libvirt manager.
        @raise ClusterManagerException: when fails
        '''
        try:
            for v in self.hosts.itervalues():
                h = v[0]
                hn = copy(h.name())
                LOGGER.info("Destroying and undefining machine %s." % hn)
                h.destroy()
                h.undefine()
                LOGGER.info("Done.")

            if len(self.hosts):
                LOGGER.info("Deleting images tmp files form disk.")
                self.hosts.clear()
                LOGGER.info("Done.")

            for n in self.nets.itervalues():
                nn = copy(n.name())
                LOGGER.info("Destroying and undefining network %s." % nn)
                n.destroy()
                n.undefine()
                LOGGER.info("Done.")

            if len(self.nets):
                self.nets.clear()

            if self.virtConnection:
                self.virtConnection.close()
        except libvirtError, e:
            msg = "Could not disconnect from libvirt: %s" % e
            LOGGER.error(msg)
            raise ClusterManagerException(msg, ERR_CONNECTION)
        else:
            LOGGER.debug("libvirt manager disconnected")
    #---------------------------------------------------------------------------
    def copyHostImg(self, hostObj, tmpFile, safeCounter = None):
        LOGGER.info(("Start copying %s (for %s) to tmp img %s") \
                    % (hostObj.diskImage, hostObj.name, tmpFile.name))
        try:
            f = open(hostObj.diskImage, "r")
        except IOError, e:
            msg = "Can't open %s. %s" % (hostObj.diskImage, e)
            raise ClusterManagerException(msg)
        #buffsize = 52428800 #read 50 MB at a time
        buffsize = (1024 ** 3) /2  #read/write 512 MB at a time
        buff = f.read(buffsize)
        while buff:
            tmpFile.file.write(buff)
            buff = f.read(buffsize)
        f.close()
        LOGGER.info(("Disk image %s  (for %s) copied to temp file %s") \
                    % (hostObj.diskImage, hostObj.name, tmpFile.name))
        if safeCounter:
            safeCounter.inc()
    #---------------------------------------------------------------------------
    def defineHost(self, hostObj, maintenance):
        '''
        Defines virtual host in a cluster using given host object, 
        not starting it. Host may be defined only once in the system.
        @param hostObj: ClusterManager.Host object
        @raise ClusterManagerException: when fails
        @return: host object from libvirt lib
        '''
        if self.hosts.has_key(hostObj.name):
            return self.hosts[hostObj.name][0]

        if maintenance:
            for h in self.hosts.itervalues():
                if h[2].diskImage == hostObj.diskImage:
                    return h[0]

        tmpFile = None
        if not maintenance:
            # first, copy the original disk image
            tmpFile = NamedTemporaryFile(prefix=self.tmpImagesPrefix, \
                                         dir=self.tmpImagesDir)
            hostObj.runningDiskImage = tmpFile.name
        else:
            LOGGER.info(("Defining host %s on ORIGINAL IMAGE %s") \
                        % (hostObj.diskImage, hostObj.name))
            hostObj.runningDiskImage = hostObj.diskImage

        self.hosts[hostObj.name] = None
        try:
            conn = self.virtConnection
            host = conn.defineXML(hostObj.xmlDesc)

            self.hosts[hostObj.name] = (host, tmpFile, hostObj, maintenance)
        except libvirtError, e:
            try:
                host = conn.lookupByName(hostObj.name)
                self.hosts[hostObj.name] = (host, "", None, None)
            except libvirtError, e:
                msg = ("Could not define host neither " + \
                        "obtain host definition: %s") % e
                raise ClusterManagerException(msg, ERR_ADD_HOST)
        return self.hosts[hostObj.name]
    #---------------------------------------------------------------------------
    def removeHost(self, hostName):
        '''
        Can not be used inside loop iterating over hosts!
        @param hostName:
        '''
        try:
            h = self.hosts[hostName][0]
            LOGGER.info("Destroying and undefining machine %s." % hostName)
            h.destroy()
            h.undefine()
            LOGGER.info("Done.")

            del self.hosts[hostName]

        except libvirtError, e:
            msg = "Could not remove virtual host: %s" % e
            LOGGER.error(msg)
            raise ClusterManagerException(msg, ERR_CONNECTION)
    #---------------------------------------------------------------------------
    def defineNetwork(self, netObj):
        '''
        Defines network object without starting it.
        @param xml: libvirt XML cluster definition
        @raise ClusterManagerException: when fails
        @return: None
        '''
        if netObj.name in self.nets:
            return self.nets[netObj.name]

        try:
            conn = self.virtConnection
            self.nets[netObj.name] = conn.networkDefineXML(netObj.xmlDesc)
            LOGGER.info("Defining network " + netObj.name)
        except libvirtError, e:
            LOGGER.error("Couldn't define network: %s" % e)
            try:
                self.nets[netObj.name] = conn.networkLookupByName(netObj.name)
            except libvirtError, e:
                LOGGER.error(e)
                msg = "Could not define net neither obtain net definition. " + \
                      " After network already exists."
                raise ClusterManagerException(msg, ERR_CREATE_NETWORK)

        return self.nets[netObj.name]
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
            msg = "Could not define network from XML: %s" % e
            LOGGER.error(msg)
            raise ClusterManagerException(msg, ERR_CREATE_NETWORK)

        if net and net.isActive():
            LOGGER.info("Network %s created and active." % (networkObj.name))

        return net
    #---------------------------------------------------------------------------
    def removeNetwork(self, netName):
        '''
        Can not be used inside loop iterating over networks!
        @param hostName:
        '''
        try:
            n = self.nets[netName]
            LOGGER.info("Destroying and undefining network %s." % netName)
            n.destroy()
            n.undefine()
            LOGGER.info("Done.")
            del self.nets[netName]

        except libvirtError, e:
            msg = "Could not destroy network from libvirt: %s" % e
            LOGGER.error(msg)
            raise ClusterManagerException(msg, ERR_CONNECTION)
    #---------------------------------------------------------------------------
    def createCluster(self, cluster, maintenance=False):
        '''
        Creates whole cluster: first network, then hosts.
        @param cluster:
        '''
        self.createNetwork(cluster.network)

        if cluster.hosts and len(cluster.hosts):
            copyThreads = {}
            safeCounter = SafeCounter()
            for h in cluster.hosts:
                self.defineHost(h, maintenance)

                if not maintenance:
                    sys.setcheckinterval(500)
                    copyThreads[h.name] =\
                        threading.Thread(target=self.copyHostImg, args =\
                                         (self.hosts[h.name][2], \
                                          self.hosts[h.name][1], \
                                          safeCounter))
                    copyThreads[h.name].start()

            if not maintenance:
                #wait for all threads to copy images
                n = 0
                m = len(cluster.hosts)
                while(n < m):
                    n = safeCounter.get()
                    LOGGER.info("Machines images copied: %s of %s" % (n, m))
                sys.setcheckinterval(100)
            #start all domains
            for h in cluster.hosts:
                LOGGER.info("Starting %s" % h.name)
                self.hosts[h.name][0].create()
                LOGGER.info("Started %s" % h.name)

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

                    mod = __import__(modName, globals(), {}, ['getCluster'])
                    cl = mod.getCluster()
                    cl.definitionFile = modFile
                    #after load, check if cluster definition is correct
                    cl.validateStatic()
                    clusters.append(cl)
                except AttributeError, e:
                    LOGGER.error(e)
                    raise ClusterManagerException("Method getCluster " + \
                          "can't be found in file: " + str(modFile))
                except ImportError, e:
                    LOGGER.error("Can't import %s: %s." % (modName, e))
    for clu in clusters:
        n = [c.name for c in clusters \
                    if clu.network.name == c.network.name or
                       clu.network.bridgeName == c.network.bridgeName or
                       clu.network.ip == c.network.ip]
        n.remove(clu.name)
        if len(n) != 0:
            raise ClusterManagerException(
                    ("Cluster's %s some network's %s parameters doubled" + \
                    " in %s") % (clu.name, clu.network.name, ",".join(n)))

    return clusters

