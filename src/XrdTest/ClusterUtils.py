#!/usr/bin/env python
#-------------------------------------------------------------------------------
#
# Copyright (c) 2011-2012 by European Organization for Nuclear Research (CERN)
# Author: Lukasz Trzaska <ltrzaska@cern.ch>
#
# This file is part of XrdTest.
#
# XrdTest is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# XrdTest is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with XrdTest.  If not, see <http://www.gnu.org/licenses/>.
#
#-------------------------------------------------------------------------------
#
# File:   ClusterManager module
# Desc:   Virtual machines clusters manager.
#-------------------------------------------------------------------------------
from Utils import get_logger
LOGGER = get_logger(__name__)

import Utils
import logging
import os
import sys

from Utils import State
from string import join

# Global error types
ERR_UNKNOWN = 1
ERR_CONNECTION = 2
ERR_ADD_HOST = 4
ERR_CREATE_NETWORK = 8

class ClusterManagerException(Exception):
    '''
    General Exception raised by module
    '''
    def __init__(self, desc, typeFlag=ERR_UNKNOWN):
        '''
        Constructs Exception
        @param desc: description of an error
        @param typeFlag: represents type of an error, taken from class constants
        '''
        self.desc = desc
        self.type = typeFlag

    def __str__(self):
        '''
        Returns textual representation of an error
        '''
        return repr(self.desc)

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
          <hostname>vagabond.cern.ch</hostname>
      </host>
      %(dnshostsxml)s
  </dns>
  <bridge name="%(bridgename)s" />
  <forward />
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

    def addDnsHost(self, host):
        hostup = (host.ip, host.name)
        self.DnsHosts.append(hostup)

    def addDHCPHost(self, host):
        hostup = (host.mac, host.ip, host.name)
        self.DHCPHosts.append(hostup)

    def addHost(self, host):
        '''
        Add host to network. First to DHCP and then to DNS.
        @param host: tuple (MAC address, IP address, HOST fqdn)
        '''
        self.addDHCPHost(host)
        self.addDnsHost(host)

    def addHosts(self, hostsList):
        '''
        Add hosts to network.
        @param param: hostsList
        '''
        for h in hostsList:
            self.addHost(h)

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
      <address type='pci' domain='0x0000' bus='0x00' slot='0x03' function='0x0'/>
      <model type='virtio'/>
    </interface>
    <input type='mouse' bus='ps2'/>
    <!-- VIDEO SECTION - NORMALLY NOT NEEDED -->
    <graphics type='vnc' port='5900' autoport='yes' keymap='en-us'/>
    <video>
    <model type='cirrus' vram='9216' heads='1' />
    <address type='pci' domain='0x0000' bus='0x00' slot='0x02' function='0x0' />
    </video>
    <!-- END OF VIDEO SECTION -->
    <memballoon model='virtio'>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x04'
      function='0x0'/>
    </memballoon>
  </devices>
</domain>

"""

    def __init__(self, name="", ip="", mac="", net="", ramSize="", arch="", \
                 bootImage=None, cacheBootImage=True, emulatorPath="", uuid=""):
        self.uuid = uuid
        self.name = name
        self.ip = ip
        self.mac = mac
        self.ramSize = ramSize
        self.arch = arch
        self.bootImage = bootImage
        self.cacheBootImage = cacheBootImage
        self.net = net
        self.emulatorPath = emulatorPath

        #filled automatically
        self.clusterName = ""
        self.disks = {}
        self.runningDiskImage = ""

        # private properties
        self.__xmlDesc = ""

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

    @property
    def xmlDesc(self):
        values = self.__dict__
        values['uname'] = self.uname
        values['net'] = self.clusterName + "_" + self.net
        self.__xmlDesc = self.xmlDomainPattern % values

        return self.__xmlDesc

class Disk(object):
    
    def __init__(self, name, size, cache=True):
        self.name = name
        self.size = size
        self.cache = cache

class Cluster(Utils.Stateful):

    S_ACTIVE = (10, "Cluster active")
    S_ERROR = (-10, "Cluster error")
    S_ERROR_START = (-11, "Cluster error at start")
    S_ERROR_STOP = (-12, "Cluster error at stop")
    S_UNKNOWN = (1, "Cluster state unknown")
    S_UNKNOWN_NOHYPERV = (1, "Cluster state unknown, no hypervisor to plant it on")
    S_DEFINITION_SENT = (2, "Cluster definition sent to hypervisor to start")
    S_ACTIVE = (2, "Cluster active")
    S_STOPPED = (3, "Cluster stopped")
    S_STOPCOMMAND_SENT = (4, "Cluster stop command sent to cluster")
    '''
    Represents a cluster comprised of hosts connected through network.
    '''

    def randMac(self, history=[]):
        import random

        history.append(':'.join(map(lambda x: "%02x" % x, \
                            [ 0x00, 0x16, 0x3E, random.randint(0x00, 0x7F), \
                             random.randint(0x00, 0xFF), random.randint(0x00, 0xFF) ])))

    def __init__(self):
        Utils.Stateful.__init__(self)
        self.hosts = []
        self.name = None
        self.info = None

        self.defaultHost = Host()
        
        self.__network = None

    def addHost(self, host):
        from uuid import uuid1

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
        if not (hasattr(host, "bootImage") or host.bootImage) \
            or not (hasattr(host, "bootImage") or self.defaultHost.bootImage):
            raise ClusterManagerException(('Machine %s definition nor ' + \
                                           'cluster %s has disk image ' + \
                                          'defined') % (host.name, self.name))
        host.clusterName = self.name
        self.hosts.append(host)

    def addHosts(self, hosts):
        for h in hosts:
            self.addHost(h)

    def networkSet(self, net):
        net.clusterName = self.name
        self.defaultHost.net = net.name
        self.__network = net

    def networkGet(self):
        return self.__network
    network = property(networkGet, networkSet)

    def setEmulatorPath(self, emulator_path):
        if len(self.hosts):
            for h in self.hosts:
                h.emulatorPath = emulator_path

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

    def validateDynamic(self):
        '''
        Check if Cluster definition is semantically correct i.e. on the
        hypervisor's machine e.g. if disk images really exists on
        the machine it's to be planted.
        '''
        if self.hosts:
            for h in self.hosts:
                c1 = (h.bootImage and not os.path.exists(h.bootImage))
                c2 = (self.defaultHost.bootImage and \
                      not os.path.exists(self.defaultHost.bootImage))
                if c1 or c2:
                    return (False, ("One of disk images %s, %s" + \
                                    "has to exist") % \
                                    (h.bootImage, self.defaultHost.bootImage))

        return (True, "")

def extractClusterName(path):
    (modPath, modFile) = os.path.split(path)
    modPath = os.path.abspath(modPath)
    (modName, ext) = os.path.splitext(modFile)
    return (modName, ext, modPath, modFile)

def loadClusterDef(fp, clusters, validateWithRest=True):
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
            raise ClusterManagerException("Can't import %s: %s." % \
                                           (modName, e))
        except NameError, e:
            raise ClusterManagerException("Name error while " + \
                                          "cluster  %s import: %s." % \
                                           (modName, e))
        except Exception, e:
            raise ClusterManagerException("Error during" + \
                  " test suite %s import: %s" % (modFile, e))
    elif ext == ".pyc":
        return None
    else:
        raise ClusterManagerException("%s is not cluster definition." % \
                                       (modFile))
    return cl

def loadClustersDefs(path):
    '''
    Loads cluster definitions from .py files stored in path directory
    @param path: path for .py files, storing cluster definitions
    '''
    clusters = []
    if os.path.exists(path):
        for f in os.listdir(path):
            if not f.startswith('cluster'):
                continue
            fp = path + os.sep + f
            try:
                clu = loadClusterDef(fp, clusters)
                if clu:
                    clusters.append(clu)
            except ClusterManagerException, e:
                raise e

    return clusters
