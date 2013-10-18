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
# Desc:   Virtual machines cluster manager. Utilizes libvirt to create and 
#         remove virtual machines and networks.
#         Creation of one cluster manager may be considered as a session, during
#         which some machines and networks are created. Cluster Manager keeps
#         information of all created clusters during the session and can remove
#         all of them on demand - come back to state before it began.
#-------------------------------------------------------------------------------
"""
.. module:: ClusterManager
   :platform: Linux
   :synopsis: Module description here

.. moduleauthor:: Justin Lewis Salmon <jsalmon@cern.ch>


"""
from Utils import Logger
LOGGER = Logger(__name__).setup()

try:
    import sys
    import os
    import re
    import threading
    import libvirt
    
    from ClusterUtils import ClusterManagerException, Cluster
    from ClusterUtils import ERR_CONNECTION, ERR_ADD_HOST, ERR_CREATE_NETWORK
    from Utils import Command, State
    from SocketUtils import XrdMessage
    from copy import deepcopy
    from libvirt import libvirtError
except ImportError, e:
    LOGGER.error(str(e))
    sys.exit(1)


class ClusterManager:
    '''
    Virtual machines clusters' manager
    '''
    def __init__(self):
        '''
        Creates Manager instance. Needs url to virtual virt domains manager
        '''
        # Socket reference back to the master, for publishing status updates
        self.sockStream = None
        # definitions of clusters. Key: name Value: cluster definition
        self.clusters = {}
        # dictionary of currently running hosts. Key: hostObj.uname
        self.hosts = {}
        # dictionary of currently running networks. Key: networkObj.uname
        self.nets = {}
        self.storagePool = ''

    def virtconnect(self, url="qemu:///system"):
        '''
        Creates and returns connection to virtual machines manager
        @param url: connection url
        @raise ClusterManagerException: when fails to connect
        @return: None
        '''
        try:
            virtConnection = libvirt.open(url)
            return virtConnection
        except libvirtError, e:
            LOGGER.error("Can not connect to libvirt (-c qemu:///system): %s" % e)

    def disconnect(self):
        '''
        Undefines and removes all virtual machines and networks created
        by this cluster manager and disconnects from libvirt manager.
        @raise ClusterManagerException: when fails
        '''
        err = ''
        clusters = deepcopy(self.clusters)
        for clusterName in clusters:
            try:
                self.removeCluster(clusterName)
            except ClusterManagerException, e:
                err += ',' + str(e)
        if err:
            LOGGER.error(err)

    def copyImg(self, huName):
        '''
        Method runnable in separate threads, to separate copying of source
        operating system image to a temporary image.
        
        @param huName: host.uname - host unique name
        '''
        (host, cacheImg, hostObj) = self.hosts[huName]
        dip = self.clusters[hostObj.clusterName].defaultHost.bootImage
        
        self.updateState(Cluster.S_COPYING_IMAGES, hostObj.clusterName)
        LOGGER.info(("Start copying %s (for %s) to cache image %s") \
                    % (dip, hostObj.uname, cacheImg))
        try:
            f = open(dip , "r")
            cacheImgFile = open(cacheImg, 'w')
            #buffsize = 52428800 #read 50 MB at a time
            buffsize = (1024 ** 3) / 2  #read/write 512 MB at a time
            buff = f.read(buffsize)
            while buff:
                cacheImgFile.write(buff)
                buff = f.read(buffsize)
            f.close()
            cacheImgFile.close()
        except IOError, e:
            msg = "Can't open %s: %s" % (dip, e)
            raise ClusterManagerException(msg)
        else:
            LOGGER.info(("Disk image %s  (for %s) copied to cache file %s") \
                        % (dip, hostObj.name, cacheImg))
                
    def defineHost(self, host):
        '''
        Defines virtual host in a cluster using given host object,
        not starting it. Host with the given name may be defined once
        in the system. Stores hosts objects in class property self.hosts.
        
        @param host: ClusterManager.Host object
        @raise ClusterManagerException: when fails
        @return: host object from libvirt lib
        '''
        if self.hosts.has_key(host.uname):
            return self.hosts[host.uname][0]

        for h in self.hosts.itervalues():
            # get disk image path from cluster definition
            cip = self.clusters[host.clusterName].defaultHost.bootImage
            # if machine has any disk image given?
            if h[2].runningDiskImage == host.bootImage or \
                (not host.bootImage and h[2].runningDiskImage == cip):
                return h[0]

        if not host.bootImage:
            host.runningDiskImage = os.path.join(self.findStoragePool(\
                                    self.storagePool), '%s.img.cache' % (host.uname))
        else:
            # machine uses original source image
            LOGGER.info(("Defining machine %s using original image %s") \
                        % (host.uname, host.bootImage))
            host.runningDiskImage = os.path.join(self.findStoragePool(self.storagePool), host.bootImage)

        self.hosts[host.uname] = None
        try:
            conn = self.virtconnect()
            hostdef = conn.defineXML(host.xmlDesc)

            # add host definition objects to dictionary
            # key: host.uname - unique name
            self.hosts[host.uname] = (hostdef, host.runningDiskImage, host)
            LOGGER.info("Defined machine: %s" % host.uname)
        except libvirtError, e:
            try:
                # that is possible that machine was already created
                # if so, find it and safe the definition
                hostdef = conn.lookupByName(host.uname)
                self.hosts[host.uname] = (hostdef, None, host)
                LOGGER.info("Machine already defined: %s" % host.uname)
            except libvirtError, e:
                msg = ("Can't define machine %s on image %s nor " + \
                        "obtain machine definition: %s") % \
                        (host.uname, host.runningDiskImage, e)
                raise ClusterManagerException(msg, ERR_ADD_HOST)
        return self.hosts[host.uname]

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

            del self.hosts[hostUName]
        except libvirtError, e:
            msg = "Could not remove virtual machine: %s" % e
            LOGGER.error(msg)
            raise ClusterManagerException(msg, ERR_CONNECTION)

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
            conn = self.virtconnect()
            self.nets[netObj.uname] = conn.networkDefineXML(netObj.xmlDesc)
            LOGGER.info("Defining network " + netObj.uname)
        except libvirtError, e:
            LOGGER.error("Couldn't define network: %s" % e)
            try:
                self.nets[netObj.uname] = conn.networkLookupByName(netObj.uname)
            except libvirtError, e:
                LOGGER.error(e)
                msg = ("Could not define net %s nor obtain net definition: " + \
                      " %s") % (netObj.uname, e)
                raise ClusterManagerException(msg, ERR_CREATE_NETWORK)

        return self.nets[netObj.uname]

    def createNetwork(self, networkObj, clusterName):
        '''
        Creates and starts cluster's network. It utilizes defineNetwork
        at first and doesn't create network definition if it already exists.
        @param networkObj: Network object
        @raise ClusterManagerException: when fails
        @return: None
        '''
        self.updateState(Cluster.S_CREATING_NETWORK, clusterName)
        
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

    def removeDanglingHost(self, hostObj):
        '''
        Remove already defined host, if it has name the same as hostObj.
        @param hostObj:
        '''
        host = None
        try:
            conn = self.virtconnect()
            host = conn.lookupByName(hostObj.uname)
            LOGGER.info("Machine already defined: %s" % hostObj.uname)
        except libvirtError, e:
            # It's OK that the host isn't defined.
            LOGGER.debug(e)
            return
        
        if host:
            LOGGER.info("Old host %s definition found. Removing." % \
                        hostObj.uname)
            if host.isActive():
                host.destroy()
            host.undefine()

    def removeDanglingNetwork(self, netObj):
        '''
        Remove already defined network, if it has name the same as netObj.
        @param hostObj:
        '''
        net = None
        try:
            conn = self.virtconnect()
            net = conn.networkLookupByName(netObj.uname)
            LOGGER.info("Network already defined: %s" % netObj.uname)
        except libvirtError, e:
            # It's OK that the network isn't defined.
            LOGGER.debug(e)
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
        self.removeDanglingNetwork(cluster.network)
        for h in cluster.hosts:
            self.removeDanglingHost(h)

        if self.clusters.has_key(cluster.name):
            raise ClusterManagerException(("Cluster %s already exists." + \
                              " Needs to be destroyed first.") % \
                              (cluster.name))
            
        self.clusters[cluster.name] = cluster
        try:
            net = self.createNetwork(cluster.network, cluster.name)
        except ClusterManagerException, e:
            LOGGER.error(e)
            raise e

        if not net:
            raise ClusterManagerException(("Network %s couldn't be created." + \
                                          " Stopping cluster %s creation.") % \
                                          (cluster.network.uname, cluster.name))
            return

        self.updateState(Cluster.S_CREATING_SLAVES, cluster.name)
        try:
            if cluster.hosts and len(cluster.hosts):
                # number of machines that need additional thread to copy their 
                # source images
                needCopy = []
                
                waitingForCreate = []
                
                for h in cluster.hosts:
                    self.defineHost(h)
                    waitingForCreate.append(h.uname)
                        
                    if h.bootImage:
                        # machine defines custom boot image
                        LOGGER.info("Using custom image %s for machine %s." % \
                                    (h.bootImage, h.uname))
                        # get full path from storage pool
                        h.bootImage = self.findStorageVolume(self.storagePool, h.bootImage)
                    else:
                        # machine uses default boot image
                        LOGGER.info("Using default image %s for machine %s." % \
                                    (cluster.defaultHost.bootImage, h.uname))
                        # get full path from storage pool
                        h.bootImage = cluster.defaultHost.bootImage   
                    
                    if h.cacheBootImage:
                        # machine uses cached image
                        LOGGER.info("Retrieving cached image for machine %s." % (h.uname))
                        
                        try: 
                            self.findStorageVolume(self.storagePool, h.uname + '.img.cache')
                        except:
                            # make a copy from original image
                            LOGGER.info("Cached image doesn't exist for machine %s. Copying from %s" % \
                                        (h.uname, h.bootImage))
                            needCopy.append( h )

                #wait for all threads to copy images
                n = 0
                for h in needCopy:
                    self.copyImg(h.uname)
                    n += 1
                    LOGGER.info("Machines images copied: %d of %d" % (n, len(needCopy)))


                # remember locally domains created correctly to remove them
                # in case one can't be created
                hostsCreated = []

                for host in cluster.hosts:
                    self.createDisks(host)

                try:
                    # start machines - in libvirt aka create domains
                    for huname in waitingForCreate:
                        LOGGER.info("Creating machine %s..." % huname)
                        self.hosts[huname][0].create()
                        hostsCreated.append(huname)
                except libvirtError, e:
                    LOGGER.error("Error occured. Undefining created machines.")
                    innerErrMsg = self.removeHosts(hostsCreated)
                    self.removeCluster(cluster)
                    raise ClusterManagerException("Error during " + \
                          "creation of machine %s: %s. %s" % \
                          (h.uname, e, innerErrMsg))
                
                self.updateState(Cluster.S_ATTACHING_DISKS, cluster.name)
                try:
                    for host in cluster.hosts:
                        self.attachDisks(host)
                except ClusterManagerException, e:
                    raise e
            else:
                LOGGER.warning("No hosts in cluster defined.")
        except ClusterManagerException, e:
            LOGGER.error(e)
            self.removeNetwork(cluster.network.uname)
            raise e

    def removeCluster(self, clusterName):
        if not self.clusters.has_key(clusterName):
            LOGGER.error(("No cluster %s defined via cluster manager.") % clusterName)
            return 
        
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
            raise ClusterManagerException("Error during cluster " + \
                                          "removal: %s" % removeErr) 
        else:
            del self.clusters[clusterName]

    def createDisks(self, host):
        if len(host.disks):
            LOGGER.info('Creating storage disks to machine %s' % host.uname)
            
            for disk in host.disks:
                try:
                    self.createDisk(host.uname, disk.name, disk.size, disk.cache)
                    LOGGER.info('Created storage disk.')
                except (ClusterManagerException, Exception), e:
                    raise ClusterManagerException('Failure creating disks: %s' % e)

    def createDisk(self, host, diskName, diskSize, cache):
        diskPath = os.path.join(self.findStoragePool(self.storagePool), \
                                '%s_%s' % (host, diskName))

        if not os.path.exists(diskPath) or not cache:
            LOGGER.info('Creating storage disk %s_%s' % (host, diskName))

            try:
                with open(diskPath, 'w') as f:
                    f.truncate(int(diskSize))
                Command('mkfs.ext4 -F %s' % diskPath, '.').execute()
            except Exception, e:
                LOGGER.error(e)
                raise ClusterManagerException('Disk creation error: %s' % e)
            
    def attachDisks(self, host):
        
        if len(host.disks):
            LOGGER.info('Attaching storage disks to machine %s' % host.uname)
            
            for disk in host.disks:
                try:
                    self.attachDisk(host.uname, disk.name, disk.device)
                    LOGGER.info('Attached storage disk.')
                except (ClusterManagerException, Exception), e:
                    raise ClusterManagerException('Failure attaching disks: %s' % e)
        
    def attachDisk(self, host, diskName, device):
        ''' 
        :param host: name of the host to attach to
        '''
        diskPath = os.path.join(self.findStoragePool(self.storagePool), \
                                '%s_%s' % (host, diskName))
        
        output = Command('virsh attach-disk %s %s %s' % 
                (host, diskPath, device), '.').execute()
        if output[1] != 0:
            raise ClusterManagerException('Attaching disk failed: %s' % output)

            
    def updateState(self, state, clusterName):
        ''' Send a progress update message to the master. '''
        msg = XrdMessage(XrdMessage.M_CLUSTER_STATE)
        msg.state = State(state)
        msg.clusterName = clusterName
        try:
            self.sockStream.send(msg)
        except Exception, e:
            LOGGER.error('Error updating state: %s' % e)
    
    def getPoolPath(self, poolXML):
        '''Parse the given storage pool XML description and return its
        path. '''
        from xml.dom.minidom import parseString
        doc = parseString(poolXML)
        return doc.getElementsByTagName('target')[0].getElementsByTagName('path')[0].firstChild.nodeValue
    
    def findStoragePool(self, poolname):
        '''Attempt to find a storage pool with the given name. '''
        con = self.virtconnect()
        pool = ''
        
        try:
            pools = con.listStoragePools()
            for p in pools:
                if p == poolname:
                    pool = con.storagePoolLookupByName(poolname)
            
            if not pool:
                LOGGER.warning('Storage pool %s not found. Using default.' % poolname)
                pool = con.storagePoolLookupByName('default')
            
            poolXML = pool.XMLDesc(0)
            path = self.getPoolPath(poolXML)
            return path

        except libvirtError, e:
            raise ClusterManagerException(e)
            
    
    def findStorageVolume(self, poolname, volumename):
        '''Attempt to find a storage volume (file) in the specified libvirt storage
        pool. If the volume is not found, the default pool will be searched. Return
        the full path to the volume.'''
        con = self.virtconnect()
        pool = ''
        volume = ''
        
        try:
            pools = con.listStoragePools()
            for p in pools:
                if p == poolname:
                    pool = con.storagePoolLookupByName(poolname)
            
            if not pool:
                LOGGER.warning('Storage pool %s not found. Using default.' % poolname)
                pool = con.storagePoolLookupByName('default')
        
            # The pool might have changed, so refresh it
            pool.refresh(0)
            volumes = pool.listVolumes()
            for v in volumes:
                if v == volumename:
                    volume = pool.storageVolLookupByName(v)
                    volume = volume.path()
                    
            if not volume:
                raise ClusterManagerException(('Volume %s not found in pool %s or in the default pool.' \
                                               % (volumename, poolname)))
            return volume
            
        except libvirtError, e:
            raise ClusterManagerException(e)
            
    
    
