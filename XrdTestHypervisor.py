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
# Logging settings
#-------------------------------------------------------------------------------
import logging
import sys

logging.basicConfig(format='%(asctime)s %(levelname)s ' + \
                    '[%(filename)s %(lineno)d] ' + \
                    '%(message)s', level=logging.INFO)
LOGGER = logging.getLogger(__name__)
LOGGER.debug("Running script: " + __file__)
#------------------------------------------------------------------------------ 
try:
    from lib.Daemon import Daemon, readConfig, DaemonException, Runnable
    from lib.SocketUtils import FixedSockStream, XrdMessage, SocketDisconnectedError
    from optparse import OptionParser
    from lib.ClusterManager import ClusterManager
    from lib.ClusterUtils import ClusterManagerException, Cluster
    import ConfigParser
    import Queue
    import os
    import socket
    import ssl
    import threading
    from lib.Utils import State
except ImportError, e:
    LOGGER.error(str(e))
    sys.exit(1)
#------------------------------------------------------------------------------ 
# Globals and configurations
currentDir = os.path.dirname(os.path.abspath(__file__))
os.chdir(currentDir)
# Default daemon configuration
defaultConfFile = './XrdTestHypervisor.conf'
defaultPidFile = '/var/run/XrdTestHypervisor.pid'
defaultLogFile = '/var/log/XrdTest/XrdTestHypervisor.log'

#-------------------------------------------------------------------------------
class TCPReceiveThread(object):
    #---------------------------------------------------------------------------
    def __init__(self, sock, recvQueue):
        '''
        @param sock:
        @param recvQueue:
        '''
        self.sockStream = sock
        self.stopEvent = threading.Event()
        self.stopEvent.clear()
        self.recvQueue = recvQueue
    #---------------------------------------------------------------------------
    def close(self):
        self.stopEvent.set()
    #---------------------------------------------------------------------------
    def run(self):
        while not self.stopEvent.isSet():
            try:
                msg = self.sockStream.recv()
                LOGGER.debug("Received raw: " + str(msg))
                self.recvQueue.put(msg)
            except SocketDisconnectedError, e:
                msg = XrdMessage(XrdMessage.M_DISCONNECT)
                self.recvQueue.put(msg)
                LOGGER.info("Connection to XrdTestMaster closed.")
                break
#-------------------------------------------------------------------------------
class XrdTestHypervisor(Runnable):
    '''
    Test Hypervisor main executable class.
    '''
    #---------------------------------------------------------------------------
    # Connection with the master 
    sockStream = None
    #---------------------------------------------------------------------------
    # Blocking queue of messages received from the master
    recvQueue = Queue.Queue()
    #---------------------------------------------------------------------------
    # Config read from a file
    config = None
    #---------------------------------------------------------------------------
    # Reference to cluster manager, which is abstraction layer to 
    # virtualization library - in our case libvirt
    clusterManager = None
    #---------------------------------------------------------------------------
    def __init__(self, config):
        '''
        Initialize basic variables. Start and configure ClusterManager.
        @param config:
        '''
        self.sockStream = None
        #Blocking queue of commands received from XrdTestMaster
        self.recvQueue = Queue.Queue()
        self.config = config
        self.stopEvent = threading.Event()
        self.clusterManager = ClusterManager()
        self.clusterManager.tmpImagesDir = \
            self.config.get('virtual_machines', 'tmp_images_dir')
        self.clusterManager.tmpImagesPrefix = \
            self.config.get('virtual_machines', 'tmp_images_prefix')
        try:
            self.clusterManager.connect("qemu:///system")
        except ClusterManagerException, e:
            LOGGER.error("Can not connect to libvirt (-c qemu:///system): %s" \
                         % e)
    #---------------------------------------------------------------------------
    def __del__(self):
        self.clusterManager.disconnect()
    #---------------------------------------------------------------------------
    def connectMaster(self, masterIp, masterPort):
        '''
        Try to establish the connection with the test master.
        @param masterIp:
        @param masterPort:
        '''
        global currentDir
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sockStream = ssl.wrap_socket(sock, server_side=False,
                                        certfile=\
                                        self.config.get('security', 'certfile'),
                                        keyfile=\
                                        self.config.get('security', 'keyfile'),
                                        ssl_version=ssl.PROTOCOL_TLSv1)
            #self.sockStream = sock
            self.sockStream.connect((masterIp, masterPort))
        except socket.error, e:
            if e[0] == 111:
                LOGGER.info("Connection from master refused: Probably " + \
                            " wrong address or master not running.")
            else:
                LOGGER.info("Connection with master could not be established.")
                LOGGER.error("Socket error occured: %s" % e)
            return None
        else:
            LOGGER.debug("Connected to master.")
        try:
            #wrap sockStream into fixed socket implementation
            self.sockStream = FixedSockStream(self.sockStream)

            #authenticate in master
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
            # send my identity information
            self.sockStream.send(("hypervisor", socket.gethostname()))

            return self.sockStream
        except socket.error, e:
            LOGGER.error("Socket error occured: %s" % e)
            return None
        else:
            LOGGER.debug("Connected to master")

        return self.sockStream
    #---------------------------------------------------------------------------
    def handleStartCluster(self, msg):
        '''
        Handle start cluster message from a master - start a cluster.
        '''
        resp = XrdMessage(XrdMessage.M_CLUSTER_STATE)
        # rewrite important parameters to response message
        resp.clusterName = msg.clusterDef.name
        resp.jobGroupId = msg.jobGroupId
        resp.suiteName = msg.suiteName

        # assign rest of local constants to cluster definition
        cluster = msg.clusterDef
        cluster.setEmulatorPath(self.config.get('virtual_machines',
                                                'emulator_path'))
        cluster.network.xrdTestMasterIP = self.config.get('test_master', 'ip')
        # check if cluster definition is correct on this hypervisor
        res, msg = cluster.validateDynamic()
        if res:
            try:
                LOGGER.info("Cluster definition semantically correct. " + \
                            "Starting cluster.")
                self.clusterManager.createCluster(cluster)

                resp.state = State(Cluster.S_ACTIVE)
            except ClusterManagerException, e:
                LOGGER.error("Error occured during cluster start: %s" % e)
                resp.state = State(Cluster.S_ERROR_START, e)
        else:
            m = ("Cluster definition incorrect: %s") % msg
            LOGGER.error(m)
            resp.state = State(Cluster.S_ERROR_START, m)
        return resp
    #---------------------------------------------------------------------------
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
    #---------------------------------------------------------------------------
    def recvLoop(self):
        '''
        Main loop processing messages from master. It take out jobs
        from blocking queue of received messages, runs appropriate and 
        return answer message.
        '''
        global LOGGER
        while not self.stopEvent.isSet():
            try:
                #receive msg from master
                addrMsg = self.recvQueue.get()
                msg = addrMsg
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
                LOGGER.info("Connection to XrdTestMaster closed.")
                if self.clusterManager:
                        self.clusterManager.disconnect()
                break
    #---------------------------------------------------------------------------
    def run(self):
        '''
        Main thread. Initialize TCP threads and run recvLoop().
        '''
        sock = self.connectMaster(self.config.get('test_master', 'ip'),
                           self.config.getint('test_master', 'port'))
        if not sock:
            return

        tcpReceiveTh = TCPReceiveThread(self.sockStream, self.recvQueue)
        thTcpReceive = threading.Thread(target=tcpReceiveTh.run)
        thTcpReceive.start()

        self.recvLoop()

#-------------------------------------------------------------------------------
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

    isConfigFileRead = False
    config = ConfigParser.ConfigParser()
    #---------------------------------------------------------------------------
    # read the config file
    #---------------------------------------------------------------------------
    global defaultConfFile
    LOGGER.info("Loading config file: %s" % options.configFile)
    try:
        confFile = ''
        if options.configFile:
            confFile = options.configFile
        if not os.path.exists(confFile):
            confFile = defaultConfFile
        config = readConfig(confFile)
        isConfigFileRead = True
    except (RuntimeError, ValueError, IOError), e:
        LOGGER.error("Problem in reading config: %s" % e)
        sys.exit(1)

    testHypervisor = XrdTestHypervisor(config)
    #--------------------------------------------------------------------------
    # run the daemon
    #--------------------------------------------------------------------------
    if options.backgroundMode:
        LOGGER.info("Run in background: %s" % options.backgroundMode)

        pidFile = defaultPidFile
        logFile = defaultLogFile
        if isConfigFileRead:
            pidFile = config.get('daemon', 'pid_file_path')
            logFile = config.get('daemon', 'log_file_path')

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
    #--------------------------------------------------------------------------
    # run test master in standard mode. Used for debugging
    #--------------------------------------------------------------------------
    if not options.backgroundMode:
        testHypervisor.run()
#-------------------------------------------------------------------------------
# Start place
#-------------------------------------------------------------------------------
if __name__ == '__main__':
    main()
