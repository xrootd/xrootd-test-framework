#!/usr/bin/env python
#-------------------------------------------------------------------------------
# Author: Lukasz Trzaska <lukasz.trzaska@cern.ch>
# Date:   22.08.2011
# File:   ClusterManager module
# Desc:   Virtual machines cluster manager. Utilizes libvirt to create and 
#         remove virtual machines and networks.
#         Creation of one cluster manager may be considered as a session, during
#         which some machines and networks are created. Cluster Manager keeps
#         information of all created clusters during the session and can remove
#         all of them on demand - come back to state before it began.
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
    Virtual machines clusters' manager
    '''
    #---------------------------------------------------------------------------
    def __init__(self):
        '''
        Creates Manager instance. Needs url to virtual virt domains manager
        '''
        # holds libvirt connection of a type libvirt.virConnect
        self.virtConnection = None
        # definitions of clusters. Key: name Value: cluster definition
        self.clusters = {}
        # dictionary of currently running hosts. Key: hostObj.uname
        self.hosts = {}
        # dictionary of currently running networks. Key: networkObj.uname
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
        Undefines and removes all virtual machines and networks created
        by this cluster manager and disconnects from libvirt manager.
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
        '''
        Method runnable in separate threads, to separate copying of source 
        operating system image to a temporary image.
        @param huName: host.uname - host unique name
        @param safeCounter: thread safe counter to signalize this run finished
        '''
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
            # get disk image path from cluster definition
            cip = self.clusters[hostObj.clusterName].defaultHost.diskImage
            # if machine has any disk image given?
            if h[2].runningDiskImage == hostObj.diskImage or \
                (not hostObj.diskImage and h[2].runningDiskImage == cip):
                return h[0]

        tmpFile = None
        # machine uses copy original source image
        if not hostObj.diskImage:
            # first, copy the original disk image
            tmpFile = NamedTemporaryFile(prefix=self.tmpImagesPrefix, \
                                         dir=self.tmpImagesDir)
            hostObj.runningDiskImage = tmpFile.name
        else:
            # machine uses ogirinal source image
            LOGGER.info(("Defining machine %s using ORIGINAL IMAGE %s") \
                        % (hostObj.uname, hostObj.diskImage))
            hostObj.runningDiskImage = hostObj.diskImage

        self.hosts[hostObj.uname] = None
        try:
            conn = self.virtConnection
            host = conn.defineXML(hostObj.xmlDesc)
            
            # add host definition objects to dictionary
            # key: host.uname - unique name
            self.hosts[hostObj.uname] = (host, tmpFile, hostObj)
            LOGGER.info("Defined machine: %s" % hostObj.uname)
        except libvirtError, e:
            try:
                # that is possible that machine was already created
                # if so, find it and safe the definition
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
        @param hostUName: host.uname host unique name
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
        '''
        Remove already defined host, if it has name the same as hostObj.
        @param hostObj:
        '''
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
        '''
        Remove already defined network, if it has name the same as netObj.
        @param hostObj:
        '''
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
        Creates cluster: first network, then virtual machines - hosts.
        If it get request to create machine (host) that already exists (with the
        same name) - it removes it completely. The same story regards network.
        @param cluster: cluster definition object
        '''
        if self.clusters.has_key(cluster.name):
            raise ClusterManagerException(("Cluster %s seems to be already." + \
                              " Need to be destroyed first.") % \
                              (cluster.name))
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
                safeCounter = SafeCounter() # thread safe counter
                                        # to count how many machines have been
                                        # copied by additional threads, thus
                                        # can continue creation process

                needCopy = 0    # number of machines that need additional
                                # thread to copy their source images
                waitingForCreate = []
                for h in cluster.hosts:
                    self.removeDanglingHost(h)
                    self.defineHost(h)
                    waitingForCreate.append(h.uname)

                    # machine doesn't use original image
                    if not h.diskImage:
                        LOGGER.info("Copying image %s for machine %s." %\
                                    (cluster.defaultHost.diskImage, h.uname))
                        sys.setcheckinterval(500)
                        needCopy += 1
                        # create and start thread copying given virtual machine
                        # image to a temporary file
                        copyThreads[h.uname] =\
                            threading.Thread(target=self.copyImg, args =\
                                             (h.uname, safeCounter))
                        copyThreads[h.uname].start()
                    else: # machine uses original image
                        LOGGER.info("Using original image %s for machine %s." %\
                                    (h.diskImage, h.uname))

                #wait for all threads to copy images
                if needCopy > 0:
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
