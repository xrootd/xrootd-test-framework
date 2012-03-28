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
from Utils import SafeCounter, State
from uuid import uuid1
import random
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
        hostup = (host.ip, host.name)
        self.DnsHosts.append(hostup)
    #---------------------------------------------------------------------------
    def addDHCPHost(self, host):
        hostup = (host.mac, host.ip, host.name)
        self.DHCPHosts.append(hostup)
    #---------------------------------------------------------------------------
    def addHost(self, host):
        '''
        Add host to network. First to DHCP and then to DNS.
        @param host: tuple (MAC address, IP address, HOST fqdn)
        '''
        self.addDHCPHost(host)
        self.addDnsHost(host)
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
    def uname(self):
        '''
        Return unique name of the machine within cluster's namespace.
        '''
        if not self.clusterName:
            raise ClusterManagerException(("Can't refer to host.uname if " + \
                                          " clusterName property not " + \
                                          "defined for host ") % self.name)
        return self.clusterName + "_" + self.name
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

        values = {"name": self.uname,
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
  <name>%(uname)s</name>
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
      <mac address='%(mac)s'/>
      <source network='%(net)s'/>
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
    def __init__(self, name="", ip="", mac="", net="", \
                 diskImage=None, ramSize="", arch="", \
                 emulatorPath="", uuid=""):
        self.uuid = uuid
        self.name = name
        self.ip = ip
        self.mac = mac
        self.diskImage = diskImage
        self.ramSize = ramSize
        self.arch = arch
        self.net = net
        self.emulatorPath = emulatorPath

        #filled automatically
        self.clusterName = ""
        self.runningDiskImage = ""

        # private properties
        self.__xmlDesc = ""
    #---------------------------------------------------------------------------
    @property
    def uname(self):
        '''
        Return unique name of the machine within cluster's namespace.
        '''
        if not self.clusterName:
            raise ClusterManagerException(("Can't refer to host.uname if " + \
                                          " clusterName property not " + \
                                          "defined for host ") % self.name)
        return self.clusterName + "_" + self.name
    #---------------------------------------------------------------------------
    @property
    def xmlDesc(self):
        values = self.__dict__
        values['uname'] = self.uname
        values['net'] = self.clusterName + "_" + self.net
        self.__xmlDesc = self.xmlDomainPattern % values

        return self.__xmlDesc
#-------------------------------------------------------------------------------
class Cluster(Utils.Stateful):

    #---------------------------------------------------------------------------
    S_ACTIVE = (10, "Cluster active")
    S_ERROR = (-10, "Cluster error")
    S_ERROR_START = (-11, "Cluster error at start")
    S_ERROR_STOP = (-12, "Cluster error at stop")
    S_UNKNOWN = (1, "Cluster state unknown")
    S_UNKNOWN_NOHYPERV = (1, "Cluster state unknown, no hypervisor to plant it on")
    S_DEFINITION_SENT = (2, "Cluster definition sent do hypervisor to start")
    S_ACTIVE = (2, "Cluster active")
    S_STOPPED = (3, "Cluster stopped")
    S_STOPCOMMAND_SENT = (4, "Cluster stop command sent to cluster")
    '''
    Represents a cluster comprised of hosts connected through network.
    '''
    #---------------------------------------------------------------------------
    def randMac(self, history=[]):
        import random

        history.append(':'.join(map(lambda x: "%02x" % x, \
                            [ 0x00, 0x16, 0x3E, random.randint(0x00, 0x7F), \
                             random.randint(0x00, 0xFF), random.randint(0x00, 0xFF) ])))
    #---------------------------------------------------------------------------
    def __init__(self):
        Utils.Stateful.__init__(self)
        self.hosts = []
        self.name = None
        self.info = None

        self.defaultHost = Host()
        self.defaultHost.diskImage = None
        self.defaultHost.arch = 'x86_64'
        self.defaultHost.ramSize = '524288'
        self.defaultHost.net = None
        
        self.__network = None
    #---------------------------------------------------------------------------
    def addHost(self, host):
        if not self.network:
            raise ClusterManagerException(('First assign network ' + \
                                           'before you add hosts to cluster' + \
                                          ' %s definition.') % (self.name))
        if not hasattr(host, "uuid") or not host.uuid:
            host.uuid = str(uuid1())
        if not hasattr(host, "arch") or not host.arch:
            host.arch = self.defaultHost.arch
        if not hasattr(host, "ramSize") or not host.ramSize:
            host.ramSize = self.defaultHost.ramSize
        if not hasattr(host, "net") or not host.net:
            host.net = self.defaultHost.net
        if not (hasattr(host, "diskImage") or host.diskImage) \
            or not (hasattr(host, "diskImage") or self.defaultHost.diskImage):
            raise ClusterManagerException(('Nor machine %s definition nor ' + \
                                           'cluster %s has disk image ' + \
                                          'defined') % (host.name, self.name))
        host.clusterName = self.name
        self.hosts.append(host)
    #---------------------------------------------------------------------------
    def addHosts(self, hosts):
        for h in hosts:
            self.addHost(h)
    #---------------------------------------------------------------------------
    def networkSet(self, net):
        net.clusterName = self.name
        self.defaultHost.net = net.name
        self.__network = net
    #---------------------------------------------------------------------------
    def networkGet(self):
        return self.__network
    network = property(networkGet, networkSet)
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
            if h.mac in umacs:
                raise ClusterManagerException(('Host MAC %s address ' + \
                                               'doubled') % h.mac)
            umacs.append(h.mac)
            if h.net != self.network.name:
                raise ClusterManagerException(('Network name %s in host %s' + \
                                               ' definition not defined in' + \
                                               ' cluster %s.') % \
                                              (h.net, h.name, self.name))
        if self.network.ip == self.network.DHCPRange[0]:
            raise ClusterManagerException(('Network %s [%s] IP the ' + \
                                           'same as DHCPRange ' + \
                                           ' first address') \
                                          % (self.network.name, \
                                             self.definitionFile))
    #---------------------------------------------------------------------------
    def validateAgainstSystem(self, clusters):
        '''
        Check if cluster definition is correct with other 
        clusters defined in the system. This correctness is critical for
        cluster definition to be added.
        @param clusters:
        '''
        n = [c.name for c in clusters \
                    if self.name == c.name or \
                       self.network.name == c.network.name or \
                       self.network.bridgeName == c.network.bridgeName or \
                       self.network.ip == c.network.ip]
        if len(n) != 0:
            raise ClusterManagerException(
                    ("Cluster's %s some network's %s parameters doubled" + \
                    " in %s") % (self.name, self.network.name, ",".join(n)))
    #---------------------------------------------------------------------------
    def validateDynamic(self):
        '''
        Check if Cluster definition is semantically correct i.e. on the 
        hypervisor's machine e.g. if disk images really exists on 
        the machine it's to be planted.
        '''
        if self.hosts:
            for h in self.hosts:
                c1 = (h.diskImage and not os.path.exists(h.diskImage))
                c2 = (self.defaultHost.diskImage and \
                      not os.path.exists(self.defaultHost.diskImage))
                if c1 or c2:
                    return (False, ("One of disk images %s, %s" +\
                                    "has to exist") % \
                                    (h.diskImage, self.defaultHost.diskImage))

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
        #definitions of clusters [by name]
        self.clusters = {}
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
            err = ''
            for clusterName in self.clusters:
                try:
                    self.removeCluster(clusterName)
                except ClusterManagerException, e:
                    err += ',' + str(e)
            if err:
                LOGGER.error(err)
            if self.virtConnection:
                self.virtConnection.close()
        except libvirtError, e:
            msg = "Could not disconnect from libvirt: %s" % e
            LOGGER.error(msg)
            raise ClusterManagerException(msg, ERR_CONNECTION)
        else:
            LOGGER.debug("libvirt manager disconnected")
    #---------------------------------------------------------------------------
    def copyImg(self, huName, safeCounter = None):
        (host, tmpFile, hostObj) = self.hosts[huName]

        dip = self.clusters[hostObj.clusterName].defaultHost.diskImage
        LOGGER.info(("Start copying %s (for %s) to tmp img %s") \
                    % (dip, hostObj.uname, tmpFile.name))
        try:
            f = open(dip , "r")
            #buffsize = 52428800 #read 50 MB at a time
            buffsize = (1024 ** 3) /2  #read/write 512 MB at a time
            buff = f.read(buffsize)
            while buff:
                tmpFile.file.write(buff)
                buff = f.read(buffsize)
            f.close()
        except IOError, e:
            msg = "Can't open %s. %s" % (dip, e)
            raise ClusterManagerException(msg)
        else:
            LOGGER.info(("Disk image %s  (for %s) copied to temp file %s") \
                        % (dip, hostObj.name, tmpFile.name))
            if safeCounter:
                safeCounter.inc()
    #---------------------------------------------------------------------------
    def defineHost(self, hostObj):
        '''
        Defines virtual host in a cluster using given host object, 
        not starting it. Host with the given name may be defined once 
        in the system. Stores hosts objects in class property self.hosts.
        @param hostObj: ClusterManager.Host object
        @raise ClusterManagerException: when fails
        @return: host object from libvirt lib
        '''
        if self.hosts.has_key(hostObj.uname):
            return self.hosts[hostObj.uname][0]

        for h in self.hosts.itervalues():
            cip = self.clusters[hostObj.clusterName].defaultHost.diskImage
            if h[2].runningDiskImage == hostObj.diskImage or \
                (not hostObj.diskImage and h[2].runningDiskImage == cip):
                return h[0]

        tmpFile = None
        if not hostObj.diskImage:
            # first, copy the original disk image
            tmpFile = NamedTemporaryFile(prefix=self.tmpImagesPrefix, \
                                         dir=self.tmpImagesDir)
            hostObj.runningDiskImage = tmpFile.name
        else:
            LOGGER.info(("Defining machine %s using ORIGINAL IMAGE %s") \
                        % (hostObj.uname, hostObj.diskImage))
            hostObj.runningDiskImage = hostObj.diskImage

        self.hosts[hostObj.uname] = None
        try:
            conn = self.virtConnection
            host = conn.defineXML(hostObj.xmlDesc)

            self.hosts[hostObj.uname] = (host, tmpFile, hostObj)
            LOGGER.info("Defined machine: %s" % hostObj.uname)

        except libvirtError, e:
            try:
                host = conn.lookupByName(hostObj.uname)
                self.hosts[hostObj.uname] = (host, None, hostObj)
                LOGGER.info("Machine already defined: %s" % hostObj.uname)

            except libvirtError, e:
                msg = ("Can't define machine %s on image %s neither " + \
                        "obtain machine definition: %s") % \
                        (hostObj.uname, hostObj.runningDiskImage, e)
                raise ClusterManagerException(msg, ERR_ADD_HOST)
        return self.hosts[hostObj.uname]
    #---------------------------------------------------------------------------
    def removeHost(self, hostUName):
        '''
        Can not be used inside loop iterating over hosts!
        @param hostUName:
        '''
        try:
            h = self.hosts[hostUName][0]
            LOGGER.info("Destroying and undefining machine %s." % hostUName)
            h.destroy()
            h.undefine()
            LOGGER.info("Done.")

            del self.hosts[hostUName]

        except libvirtError, e:
            msg = "Could not remove virtual machine: %s" % e
            LOGGER.error(msg)
            raise ClusterManagerException(msg, ERR_CONNECTION)
    #---------------------------------------------------------------------------
    def removeHosts(self, hostsUnameList):
        '''
        Remove multiple hosts.
        @param hostsUnameList: list of unames of defined hosts.
        '''

        innerErrors = []
        for huName in hostsUnameList:
            try:
                self.removeHost(huName)
            except ClusterManagerException, e:
                innerErrors.append(e)

        errMsgs = map(str, innerErrors)
        errMsg = ', '.join(errMsgs)

        return errMsg
    #---------------------------------------------------------------------------
    def defineNetwork(self, netObj):
        '''
        Defines network object without starting it.
        @param xml: libvirt XML cluster definition
        @raise ClusterManagerException: when fails
        @return: None
        '''
        if netObj.uname in self.nets:
            return self.nets[netObj.uname]

        try:
            conn = self.virtConnection
            self.nets[netObj.uname] = conn.networkDefineXML(netObj.xmlDesc)
            LOGGER.info("Defining network " + netObj.uname)
        except libvirtError, e:
            LOGGER.error("Couldn't define network: %s" % e)
            try:
                self.nets[netObj.uname] = conn.networkLookupByName(netObj.uname)
            except libvirtError, e:
                LOGGER.error(e)
                msg = ("Could not define net %s neither obtain net definition. " + \
                      " After network already exists.") % netObj.uname
                raise ClusterManagerException(msg, ERR_CREATE_NETWORK)

        return self.nets[netObj.uname]
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
            LOGGER.info("Network %s created and active." % (networkObj.uname))

        return net
    #---------------------------------------------------------------------------
    def removeNetwork(self, netUName):
        '''
        Can not be used inside loop iterating over networks!
        @param hostName:
        '''
        try:
            n = self.nets[netUName]
            LOGGER.info("Destroying and undefining network %s." % netUName)
            n.destroy()
            n.undefine()
            LOGGER.info("Done.")
            del self.nets[netUName]

        except libvirtError, e:
            msg = "Could not destroy network from libvirt: %s" % e
            LOGGER.error(msg)
            raise ClusterManagerException(msg, ERR_CONNECTION)
    #---------------------------------------------------------------------------
    def removeDanglingHost(self, hostObj):
        host = None
        try:
            conn = self.virtConnection
            host = conn.lookupByName(hostObj.uname)
            LOGGER.info("Machine already defined: %s" % hostObj.uname)
        except libvirtError, e:
            return

        if host:
            LOGGER.info("Old host %s definition found. Removing." % \
                        hostObj.uname)
            if host.isActive():
                host.destroy()
            host.undefine()
    #---------------------------------------------------------------------------
    def removeDanglingNetwork(self, netObj):
        net = None
        try:
            conn = self.virtConnection
            net = conn.networkLookupByName(netObj.uname)
            LOGGER.info("Machine already defined: %s" % netObj.uname)
        except libvirtError, e:
            return

        if net:
            LOGGER.info("Old network %s definition found. Removing." % \
                        netObj.uname)
            if net.isActive():
                net.destroy()
            net.undefine()

    def createCluster(self, cluster):
        '''
        Creates whole cluster: first network, then virtual machines - hosts.
        @param cluster:
        '''
        self.clusters[cluster.name] = cluster
        self.removeDanglingNetwork(cluster.network)
        net = self.createNetwork(cluster.network)

        if not net:
            raise ClusterManagerException(("Network %s couldn't be created." + \
                                          " Stoping cluster %s creation.") % \
                                          (cluster.network.uname, cluster.name))
            return

        try:
            if cluster.hosts and len(cluster.hosts):
                copyThreads = {}
                safeCounter = SafeCounter()

                needCopy = 0    # number of machines that need additional
                                # thread to copy
                waitingForCreate = []
                for h in cluster.hosts:
                    self.removeDanglingHost(h)
                    self.defineHost(h)
                    waitingForCreate.append(h.uname)

                    LOGGER.info("Host diskimage: %s" % h.diskImage)
                    if not h.diskImage:
                        LOGGER.info("Copying image %s for machine %s." %\
                                    (cluster.defaultHost.diskImage, h.uname))
                        sys.setcheckinterval(500)
                        needCopy += 1
                        copyThreads[h.uname] =\
                            threading.Thread(target=self.copyImg, args =\
                                             (h.uname, safeCounter))
                        copyThreads[h.uname].start()
                    else:
                        LOGGER.info("Using original image %s for machine %s." %\
                                    (h.diskImage, h.uname))

                if needCopy > 0:
                    #wait for all threads to copy images
                    n = 0
                    while(n < needCopy):
                        n = safeCounter.get()
                        LOGGER.info("Machines images copied: %s of %s" %\
                                    (n, needCopy))
                    sys.setcheckinterval(100)
                # remember locally domains created correctly to remove them
                # in case one can't be created
                hostsCreated = []
                try:
                    # start machines - in libvirt aka create domains
                    for huname in waitingForCreate:
                        LOGGER.info("Creating machine %s" % huname)
                        self.hosts[huname][0].create()
                        hostsCreated.append(huname)
                        LOGGER.info("Created machine %s" % huname)
                except libvirt.libvirtError, e:
                    LOGGER.info("Error occured. Undefining created machines.")
                    innerErrMsg = self.removeHosts(hostsCreated)
                    raise ClusterManagerException("Error during "+ \
                          "creation of machine %s: %s. %s" %\
                          (h.uname, e, innerErrMsg))
            else:
                LOGGER.info("No hosts in cluster defined.")
        except ClusterManagerException, e:
            self.removeNetwork(cluster.network.uname)
            raise e
    #---------------------------------------------------------------------------
    def removeCluster(self, clusterName):
        if not self.clusters.has_key(clusterName):
            raise ClusterManagerException(("No cluster %s defined " +\
                                          " via cluster manager.") \
                                          % clusterName)
        LOGGER.info("Removing cluster %s." % clusterName)
        cluster = self.clusters[clusterName]

        removeErr = ''

        hostsToRemove = [h.uname for h in cluster.hosts]
        removeErr += self.removeHosts(hostsToRemove)

        if cluster.network and self.nets.has_key(cluster.network.uname):
            try:
                self.clusterManager.removeNetwork(cluster.network.uname)
            except ClusterManagerException, e:
                removeErr += str(e)

        if removeErr:
            raise ClusterManagerException("Errors during cluster " +\
                                          "removal: %s" % removeErr)
        else:
            del self.clusters[clusterName]
#-------------------------------------------------------------------------------
def extractClusterName(path):
    (modPath, modFile) = os.path.split(path)
    modPath = os.path.abspath(modPath)
    (modName, ext) = os.path.splitext(modFile)
    return (modName, ext, modPath, modFile)
#-------------------------------------------------------------------------------
def loadClusterDef(fp, clusters, validateWithRest = True):
    (modName, ext, modPath, modFile) = extractClusterName(fp)

    cl = None
    if os.path.isfile(fp) and ext == '.py':
        mod = None
        try:
            if not modPath in sys.path:
                sys.path.insert(0, modPath)
    
            if sys.modules.has_key(modName):
                del sys.modules[modName]
            mod = __import__(modName, globals(), {}, ['getCluster'])
    
            cl = mod.getCluster()
            if cl.name != modName:
                raise ClusterManagerException(("Cluster name %s in file %s" + \
                  " is not the same as filename <cluster_name>.py") % \
                                         (cl.name, modFile))
            cl.definitionFile = modFile
            #after load, check if cluster definition is correct
            cl.state = State(Cluster.S_UNKNOWN)
            cl.validateStatic()
            if validateWithRest:
                cl.validateAgainstSystem(clusters)
        except AttributeError, e:
            raise ClusterManagerException("AttributeError in cluster defini" + \
                  "tion file %s: %s" % (modFile, e))
        except ImportError, e:
            raise ClusterManagerException("Can't import %s: %s." %\
                                           (modName, e))
        except NameError, e:
            raise ClusterManagerException("Name error while " + \
                                          "cluster  %s import: %s." %\
                                           (modName, e))
        except Exception, e:
            raise ClusterManagerException("Error during" + \
                  " test suite %s import: %s" % (modFile, e))
    elif ext == ".pyc":
        return None
    else:
        raise ClusterManagerException("%s is not cluster definition." %\
                                       (modFile))
    return cl
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
            try:
                clu = loadClusterDef(fp, clusters)
                if clu:
                    clusters.append(clu)
            except ClusterManagerException, e:
                raise e

    return clusters
