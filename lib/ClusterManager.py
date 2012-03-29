#!/usr/bin/env python
#-------------------------------------------------------------------------------
# Author: Lukasz Trzaska <lukasz.trzaska@cern.ch>
# Date:   22.08.2011
# File:   ClusterManager module
# Desc:   Virtual machines clusters manager.
#-------------------------------------------------------------------------------
# Imports
#-------------------------------------------------------------------------------
from ClusterUtils import ClusterManagerException, \
    ERR_CONNECTION, ERR_ADD_HOST, ERR_CREATE_NETWORK
from Utils import SafeCounter
from copy import deepcopy
from tempfile import NamedTemporaryFile
import logging
import sys
import threading
import libvirt
from libvirt import libvirtError
#-------------------------------------------------------------------------------
# Global variables
#-------------------------------------------------------------------------------
logging.basicConfig(format='%(levelname)s line %(lineno)d: %(message)s', \
                    level=logging.INFO)
LOGGER = logging.getLogger(__name__)
LOGGER.debug("Running script: " + __file__)
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
            clusters = deepcopy(self.clusters)
            for clusterName in clusters:
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
                        LOGGER.info("Creating machine %s..." % huname)
                        self.hosts[huname][0].create()
                        hostsCreated.append(huname)
                        LOGGER.info("Created successfully machine %s." % huname)
                except libvirtError, e:
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
                self.removeNetwork(cluster.network.uname)
            except ClusterManagerException, e:
                removeErr += str(e)

        if removeErr:
            raise ClusterManagerException("Errors during cluster " +\
                                          "removal: %s" % removeErr)
        else:
            del self.clusters[clusterName]
