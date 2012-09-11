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
# File:    XrdTestHypervisor
# Desc:    Xroot Testing Framework Hypervisor component.
#          * daemon to manage the virtual machines clusters and their networks
#          * on demand of Master it starts/stops/configures virtual machines
#          * uses libvirt to manage virtual machines
#-------------------------------------------------------------------------------
from XrdTest.Utils import Logger
LOGGER = Logger(__name__).setup()

try:
    import logging
    import sys
    import ConfigParser
    import Queue
    import os
    import socket
    import ssl
    import threading
    import time

    from XrdTest.Daemon import Daemon, DaemonException, Runnable
    from XrdTest.TCPClient import TCPReceiveThread
    from XrdTest.SocketUtils import FixedSockStream, XrdMessage, SocketDisconnectedError
    from XrdTest.ClusterManager import ClusterManager
    from XrdTest.ClusterUtils import ClusterManagerException, Cluster
    from XrdTest.Utils import State, redirectOutput
    from optparse import OptionParser
except ImportError, e:
    LOGGER.error(str(e))
    sys.exit(1)


class XrdTestHypervisorException(Exception):
    '''
    General Exception raised by XrdTestHypervisor.
    '''
    def __init__(self, desc):
        '''
        Constructs Exception
        @param desc: description of an error
        '''
        self.desc = desc
        
    def __str__(self):
        '''
        Returns textual representation of an error
        '''
        return repr(self.desc)

class XrdTestHypervisor(Runnable):
    '''
    Test Hypervisor main executable class.
    '''
    def __init__(self, configFile, backgroundMode):
        '''
        Initialize basic variables. Start and configure ClusterManager.
        @param configFile:
        '''
        # Default configuration
        self.defaultConfFile = '/etc/XrdTest/XrdTestHypervisor.conf'
        self.defaultPidFile = '/var/run/XrdTestHypervisor.pid'
        self.defaultLogFile = '/var/log/XrdTest/XrdTestHypervisor.log'
        self.logLevel = 'INFO'
        self.storagePool = '/var/lib/libvirt/XrdTest/images'
        
        if not configFile:
            configFile = self.defaultConfFile
        self.config = self.readConfig(configFile)
        
        if self.config.has_option('daemon', 'log_level'):
            self.logLevel = self.config.get('daemon', 'log_level')
        logging.getLogger().setLevel(getattr(logging, self.logLevel))
        
        # redirect output on daemon start
        if backgroundMode:
            if self.config.has_option('daemon', 'log_file_path'):
                redirectOutput(self.config.get('daemon', 'log_file_path'))
        
        LOGGER.info("Using config file: %s" % configFile)
        
        # Connection with the master 
        self.sockStream = None
        # Blocking queue of commands received from XrdTestMaster
        self.recvQueue = Queue.Queue()
        self.stopEvent = threading.Event()
        # Reference to cluster manager, which is abstraction layer to 
        # virtualization library - in our case libvirt
        self.clusterManager = ClusterManager()
        
        if self.config.has_option('virtual_machines', 'storage_pool'):
            self.storagePool = self.config.get('virtual_machines', 'storage_pool')
        self.clusterManager.storagePool = self.storagePool

    def __del__(self):
        ''' TODO: '''
        self.clusterManager.disconnect()

    def tryConnect(self):
        ''' 
        Attempt to connect to the master. Retry every 5 seconds, up to a 
        maximum of 500 times.
        '''
        for i in xrange(500):
            LOGGER.debug('Connection attempt: %s' % str(i))
            sock = self.connectMaster(self.config.get('test_master', 'ip'),
                           self.config.getint('test_master', 'port'))
            if sock:
                tcpReceiveTh = TCPReceiveThread(self.sockStream, self.recvQueue)
                thTcpReceive = threading.Thread(target=tcpReceiveTh.run)
                thTcpReceive.start()
                self.clusterManager.sockStream = self.sockStream  
                return sock
            time.sleep(5)
        return None
        
    def connectMaster(self, masterName, masterPort):
        '''
        Try to establish the connection with the test master.

        @param masterName:
        @param masterPort:
        '''
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sockStream = ssl.wrap_socket(sock, server_side=False,
                                        certfile=\
                                        self.config.get('security', 'certfile'),
                                        keyfile=\
                                        self.config.get('security', 'keyfile'),
                                        ssl_version=ssl.PROTOCOL_TLSv1)

            self.sockStream.connect((socket.gethostbyname(masterName), masterPort))
        except socket.error, e:
            if e[0] == 111:
                LOGGER.error("%s: Probably wrong address or master not running." % e)
            else:
                LOGGER.info("Connection with master could not be established.")
                LOGGER.error("Socket error occured: %s" % e)
            return None
        else:
            LOGGER.debug("Connected to master.")
        try:
            # Wrap sockStream into fixed socket implementation
            self.sockStream = FixedSockStream(self.sockStream)
            # Send my identity information
            self.sockStream.send(("hypervisor", socket.gethostname()))
            
            #Authenticate in master
            self.sockStream.send(\
                        self.config.get('test_master', 'connection_passwd'))
            msg = self.sockStream.recv()
            LOGGER.info('Received msg: ' + msg)

            if msg == "PASSWD_OK":
                LOGGER.info("Connected and authenticated to XrdTestMaster " + \
                            "successfully. Waiting for commands " + \
                            "from the master.")
            else:
                LOGGER.info("Password authentication in master failed.")
                return None

            return self.sockStream
        except socket.error, e:
            LOGGER.error("Socket error occured: %s" % e)
            return None
        else:
            LOGGER.debug("Connected to master")

        return self.sockStream

    def handleStartCluster(self, msg):
        '''
        Handle start cluster message from a master - start a cluster.
        '''
        self.updateState(Cluster.S_STARTING_CLUSTER, msg.clusterDef.name)
        
        resp = XrdMessage(XrdMessage.M_CLUSTER_STATE)
        # rewrite important parameters to response message
        resp.clusterName = msg.clusterDef.name
        resp.jobGroupId = msg.jobGroupId
        resp.suiteName = msg.suiteName

        # assign rest of local constants to cluster definition
        cluster = msg.clusterDef
        cluster.setEmulatorPath(self.config.get('virtual_machines',
                                                'emulator_path'))
        cluster.network.xrdTestMasterIP = socket.gethostbyname( \
                                        self.config.get('test_master', 'ip'))
        
        try:
            cluster.defaultHost.bootImage = self.clusterManager.findStorageVolume( \
                                self.storagePool, cluster.defaultHost.bootImage)
        except ClusterManagerException, e:
            LOGGER.error(e)
            resp.state = State(Cluster.S_ERROR_START, e)
            return resp
            
        # check if cluster definition is correct on this hypervisor
        res, msg = cluster.validateDynamic()
        if res:
            try:
                LOGGER.info("Cluster definition semantically correct. " + \
                            "Starting cluster.")
                self.clusterManager.createCluster(cluster)
                
                resp.state = State(Cluster.S_WAITING_SLAVES)
                #self.updateState(Cluster.S_WAITING_SLAVES, resp.clusterName)
            except ClusterManagerException, e:
                LOGGER.error("Error occured during cluster start: %s" % e)
                resp.state = State(Cluster.S_ERROR_START, e)
        else:
            m = ("Cluster definition incorrect: %s") % msg
            LOGGER.error(m)
            resp.state = State(Cluster.S_ERROR_START, m)
        return resp

    def handleStopCluster(self, msg):
        '''
        Handle stop cluster message from a master - stop a running cluster.
        '''
        resp = XrdMessage(XrdMessage.M_CLUSTER_STATE)
        resp.clusterName = msg.clusterDef.name

        cluster = msg.clusterDef
        try:
            self.clusterManager.removeCluster(cluster.name)
            resp.state = State(Cluster.S_STOPPED)
        except ClusterManagerException, e:
            LOGGER.error("Error occured: %s" % e)
            resp.state = State(Cluster.S_ERROR_STOP, e)

        return resp

    def recvLoop(self):
        '''
        Main loop processing messages from master. It take out jobs
        from blocking queue of received messages, runs appropriate and
        return answer message.
        '''
        while not self.stopEvent.isSet():
            try:
                #receive msg from master
                addrMsg = self.recvQueue.get()
                msg = addrMsg

                if isinstance(msg, Exception):
                    raise msg
                
                LOGGER.info("Received msg: " + str(msg.name))

                resp = XrdMessage(XrdMessage.M_UNKNOWN)
                if msg.name is XrdMessage.M_HELLO:
                    resp = XrdMessage(XrdMessage.M_HELLO)
                elif msg.name == XrdMessage.M_START_CLUSTER:
                    resp = self.handleStartCluster(msg)
                elif msg.name == XrdMessage.M_STOP_CLUSTER:
                    resp = self.handleStopCluster(msg)
                elif msg.name == XrdMessage.M_DISCONNECT:
                    #undefine and remove all running machines
                    self.clusterManager.disconnect()
                    break
                else:
                    LOGGER.info("Received unknown message: " + str(msg.name))

                self.sockStream.send(resp)
                LOGGER.debug("Sent msg: " + str(resp))
            except SocketDisconnectedError, e:
                LOGGER.error(e)
                LOGGER.info("Connection to XrdTestMaster closed.")
                
                # Try to reconnect
                self.tryConnect()
                
                # Remove clusters
                if self.clusterManager:
                    clusters = self.clusterManager.clusters.keys()
                    for cluster in clusters:
                        self.clusterManager.removeCluster(cluster)
                    try:
                        self.clusterManager.disconnect()
                    except ClusterManagerException, e:
                        LOGGER.error(e)

    def run(self):
        '''
        Main thread. Initialize TCP threads and run recvLoop().
        '''  
        sock = self.tryConnect()
    
        if not sock:
            return

        self.recvLoop()

    def readConfig(self, confFile):
            '''
            Reads configuration from given file or from default if None given.
            @param confFile: file with configuration
            '''
            config = ConfigParser.ConfigParser()
            if os.path.exists(confFile):
                try:
                    fp = file(confFile, 'r')
                    config.readfp(fp)
                    fp.close()
                except IOError, e:
                    LOGGER.exception(e)
            else:
                raise XrdTestHypervisorException("Config file %s could not be read" % confFile)
            return config
        
    def updateState(self, state, clusterName):
        ''' Send a progress update message to the master. '''
        msg = XrdMessage(XrdMessage.M_CLUSTER_STATE)
        msg.state = State(state)
        msg.clusterName = clusterName
        self.sockStream.send(msg)

def main():
    '''
    Program begins here.
    '''
    parse = OptionParser()
    parse.add_option("-c", "--configfile", dest="configFile", type="string", \
                     action="store", help="config (.conf) file location")
    parse.add_option("-b", "--background", dest="backgroundMode", \
                     type="string", action="store", \
                      help="run runnable as a daemon")

    (options, args) = parse.parse_args()
        
    configFile = None
    if options.configFile:
        configFile = options.configFile    
    
    # Initialize the hypervisor
    testHypervisor = XrdTestHypervisor(configFile, options.backgroundMode)

    # run the daemon
    if options.backgroundMode:
        LOGGER.info("Run in background: %s" % options.backgroundMode)

        pidFile = testHypervisor.config.get('daemon', 'pid_file_path')
        logFile = testHypervisor.config.get('daemon', 'log_file_path')

        dm = Daemon("XrdTestHypervisor.py", pidFile, logFile)
        try:
            if options.backgroundMode == 'start':
                dm.start(testHypervisor)
            elif options.backgroundMode == 'stop':
                dm.stop()
            elif options.backgroundMode == 'check':
                res = dm.check()
                print 'Result of runnable check: %s' % str(res)
            elif options.backgroundMode == 'reload':
                dm.reload()
                print 'You can either start, stop, check or reload the deamon'
                sys.exit(3)
        except (DaemonException, RuntimeError, ValueError, IOError), e:
            LOGGER.error("Problem in daemon operation: %s" % e)
            sys.exit(1)

    # run test master in standard mode. Used for debugging
    if not options.backgroundMode:
        testHypervisor.run()

if __name__ == '__main__':
    main()
