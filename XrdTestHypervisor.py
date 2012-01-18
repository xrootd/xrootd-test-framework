#!/usr/bin/env python
#-------------------------------------------------------------------------------
# Author:  Lukasz Trzaska <ltrzaska@cern.ch>
# Date:    
# File:    XrdTestHypervisor
# Desc:    Xroot Testing Framework Hypervisor component.
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
    from ClusterManager import ClusterManager, ClusterManagerException, Cluster
    from Daemon import Daemon, readConfig, DaemonException, Runnable
    from SocketUtils import FixedSockStream, XrdMessage, SocketDisconnectedError
    from optparse import OptionParser
    import ConfigParser
    import Queue
    import copy
    import hashlib
    import os
    import socket
    import ssl
    import threading
    from Utils import State
except ImportError, e:
    LOGGER.error(str(e))
    sys.exit(1)

currentDir = os.path.dirname(os.path.abspath(__file__))
#Default daemon configuration
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
                LOGGER.info("Connection to XrdTestMaster closed.")
                break
#-------------------------------------------------------------------------------
class XrdTestHypervisor(Runnable):
    '''
    Test Hypervisor main executable class.
    '''
    sockStream = None
    recvQueue = Queue.Queue()
    config = None
    #---------------------------------------------------------------------------
    def __init__(self, config):
        self.sockStream = None
        #Blocking queue of commands received from XrdTestMaster
        self.recvQueue = Queue.Queue()
        self.config = config
        self.stopEvent = threading.Event()
    #---------------------------------------------------------------------------
    def connectMaster(self, masterIp, masterPort):
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
                LOGGER.info("Connection from master refused.")
            else:
                LOGGER.info("Connection with master could not be established.")
                LOGGER.exception(e)
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

            self.sockStream.send(("hypervisor", socket.gethostname()))

            return self.sockStream
        except socket.error, e:
            LOGGER.exception(e)
            return None
        else:
            LOGGER.debug("Connected to master")

        return self.sockStream
    #---------------------------------------------------------------------------
    def handleStartCluster(self, msg):

        resp = XrdMessage(XrdMessage.M_CLUSTER_STATE)
        resp.clusterName = msg.clusterDef.name

        cluster = msg.clusterDef
        cluster.setEmulatorPath(self.config.get('virtual_machines',
                                                'emulator_path'))

        cluster.network.xrdTestMasterIP = self.config.get('test_master', 'ip')
        res, msg = cluster.validateDynamic()
        if res:
            try:
                LOGGER.info("Cluster definition semantically correct. " + \
                            "Starting cluster.")
                cm = ClusterManager()
                cm.connect("qemu:///system")

                if cluster.network:
                    act = cm.networkIsActive(cluster.network)
                    LOGGER.info("Network " + cluster.network.name + \
                                    " isActive(): " + str(act))
                    if not act:
                        LOGGER.info("Creating network.")
                        cm.createNetwork(cluster.network)

                for h in cluster.hosts:
                    act = cm.hostIsActive(h)
                    LOGGER.info("Host " + h.name + " isActive(): " \
                                    + str(act))
                    if not act:
                        LOGGER.info("Adding host " + h.name)
                        cm.addHost(h)

                cm.disconnect()
            except ClusterManagerException, e:
                LOGGER.exception(e)
                resp.state = State("Error occured")

            resp.state = State(Cluster.S_ACTIVE)
        else:
            LOGGER.info("Cluster definition semantically incorrect. " + \
                        " Cannot start the cluster due to: " + str(msg))
            resp.state = State(Cluster.S_ERROR)

        return resp
    #---------------------------------------------------------------------------
    def recvLoop(self):
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
                else:
                    LOGGER.info("Received unknown message: " + str(msg.name))

                self.sockStream.send(resp)
                LOGGER.debug("Sent msg: " + str(resp))
            except SocketDisconnectedError, e:
                LOGGER.info("Connection to XrdTestMaster closed.")
                break
    #---------------------------------------------------------------------------
    def run(self):
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
        LOGGER.exception()
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
            LOGGER.exception(e)
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

